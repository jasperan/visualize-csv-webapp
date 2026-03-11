import glob
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import pandas as pd
from flask import (Flask, request, render_template, session,
                   redirect, url_for, jsonify, send_file)
from werkzeug.utils import secure_filename

from config import Config
from services import csv_service, llm_service, vector_service, collab_service, plugin_service
from services.async_analysis import start_analysis, get_all_status, clear_session

try:
    from flask_socketio import SocketIO, emit, join_room as sio_join, leave_room as sio_leave
    HAS_SOCKETIO = True
except ImportError:
    HAS_SOCKETIO = False

app = Flask(__name__)
app.config.from_object(Config)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DASHBOARD_FOLDER'], exist_ok=True)

# Discover plugins
plugin_service.discover_all(app.config)

if app.config['SECRET_KEY'] != os.environ.get('SECRET_KEY'):
    logging.warning(
        'SECRET_KEY not set via environment variable — using random fallback. '
        'Sessions will not survive restarts. Set SECRET_KEY for production.'
    )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def get_upload_path():
    """Return the path of the most recently uploaded file for this session."""
    path = session.get('upload_path')
    if not path or not os.path.isfile(path):
        return None
    # Validate the path is inside UPLOAD_FOLDER to prevent traversal
    real_path = os.path.realpath(path)
    real_folder = os.path.realpath(app.config['UPLOAD_FOLDER'])
    if not real_path.startswith(real_folder + os.sep):
        return None
    return path


def load_dataframe(max_rows=None):
    """Load the session's CSV into a DataFrame."""
    path = get_upload_path()
    if not path:
        return None
    return csv_service.parse_csv(path, nrows=max_rows)


def _cleanup_old_uploads(keep_path=None):
    """Remove uploads older than the current one for this session."""
    old_path = session.get('upload_path')
    if old_path and old_path != keep_path and os.path.isfile(old_path):
        try:
            os.remove(old_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Page Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify(error='No file part'), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify(error='No file selected'), 400
    if not allowed_file(f.filename):
        return jsonify(error='Only .csv and .tsv files are allowed'), 400

    safe_name = secure_filename(f.filename)
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    f.save(save_path)

    _cleanup_old_uploads(keep_path=save_path)

    session['upload_path'] = save_path
    session['upload_name'] = safe_name

    # Quick parse to return metadata
    df = csv_service.parse_csv(save_path, nrows=app.config['MAX_PREVIEW_ROWS'])
    col_info = csv_service.get_column_info(df)

    # Store in vector memory (non-blocking, best-effort)
    try:
        stats = csv_service.get_summary_stats(df)
        vector_service.store_dataset(app.config, safe_name, df, col_info, stats)
    except Exception:
        pass  # Vector search is optional

    return jsonify(
        success=True,
        filename=safe_name,
        rows=len(df),
        columns=len(df.columns),
        column_info=col_info,
        redirect=url_for('dashboard'),
    )


@app.route('/dashboard')
def dashboard():
    path = get_upload_path()
    if not path:
        return redirect(url_for('index'))
    filename = session.get('upload_name', 'data.csv')
    return render_template('dashboard.html', filename=filename)


# ---------------------------------------------------------------------------
# API Routes (JSON)
# ---------------------------------------------------------------------------

@app.route('/api/data')
def api_data():
    """Return paginated, optionally sorted table data."""
    df = load_dataframe(max_rows=app.config['MAX_PREVIEW_ROWS'])
    if df is None:
        return jsonify(error='No file uploaded'), 404

    # Sort server-side if requested
    sort_col = request.args.get('sort')
    sort_asc = request.args.get('sort_asc', 'true').lower() == 'true'
    if sort_col and sort_col in df.columns:
        df = df.sort_values(sort_col, ascending=sort_asc, na_position='last')

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = max(1, min(per_page, 200))

    start = (page - 1) * per_page
    end = start + per_page
    subset = df.iloc[start:end]

    return jsonify(
        columns=df.columns.tolist(),
        rows=subset.where(pd.notna(subset), None).values.tolist(),
        total_rows=len(df),
        page=page,
        per_page=per_page,
        total_pages=(len(df) + per_page - 1) // per_page,
    )


@app.route('/api/column_info')
def api_column_info():
    df = load_dataframe(max_rows=app.config['MAX_PREVIEW_ROWS'])
    if df is None:
        return jsonify(error='No file uploaded'), 404
    return jsonify(columns=csv_service.get_column_info(df))


@app.route('/api/insights')
def api_insights():
    df = load_dataframe(max_rows=app.config['MAX_PREVIEW_ROWS'])
    if df is None:
        return jsonify(error='No file uploaded'), 404
    insights = csv_service.generate_insights(df)
    # Run plugin insight hooks
    for hook_result in plugin_service.run_hooks('insight_generator', df):
        extra = hook_result.get('result', [])
        if isinstance(extra, list):
            insights.extend(extra)
    return jsonify(insights=insights)


@app.route('/api/charts')
def api_charts():
    df = load_dataframe(max_rows=app.config['MAX_PREVIEW_ROWS'])
    if df is None:
        return jsonify(error='No file uploaded'), 404
    col_info = csv_service.get_column_info(df)
    charts = csv_service.suggest_charts(df, col_info)
    # Run plugin chart hooks
    for hook_result in plugin_service.run_hooks('chart_generator', df, col_info):
        extra = hook_result.get('result', [])
        if isinstance(extra, list):
            charts.extend(extra)
    return jsonify(charts=charts)


@app.route('/api/narrative')
def api_narrative():
    """Generate an AI-written narrative summary of the dataset."""
    df = load_dataframe(max_rows=app.config['MAX_PREVIEW_ROWS'])
    if df is None:
        return jsonify(error='No file uploaded'), 404
    insights = csv_service.generate_insights(df)
    result = llm_service.generate_narrative(
        df=df,
        insights=insights,
        ollama_url=app.config['OLLAMA_BASE_URL'],
        model=app.config['OLLAMA_MODEL'],
    )
    return jsonify(result)


@app.route('/api/pii')
def api_pii():
    """Detect PII in the uploaded dataset."""
    df = load_dataframe(max_rows=app.config['MAX_PREVIEW_ROWS'])
    if df is None:
        return jsonify(error='No file uploaded'), 404
    pii = csv_service.detect_pii(df)
    return jsonify(pii=pii, has_pii=len(pii) > 0)


@app.route('/api/pii/redact', methods=['POST'])
def api_pii_redact():
    """Return data with PII redacted."""
    df = load_dataframe(max_rows=app.config['MAX_PREVIEW_ROWS'])
    if df is None:
        return jsonify(error='No file uploaded'), 404

    data = request.get_json() or {}
    columns = data.get('columns')  # None means auto-detect all
    redacted = csv_service.redact_pii(df, columns_to_redact=columns)

    page = request.args.get('page', 1, type=int)
    per_page = max(1, min(request.args.get('per_page', 50, type=int), 200))
    start = (page - 1) * per_page
    subset = redacted.iloc[start:start + per_page]

    return jsonify(
        columns=redacted.columns.tolist(),
        rows=subset.where(pd.notna(subset), None).values.tolist(),
        total_rows=len(redacted),
        redacted_columns=list(columns.keys()) if columns else list(csv_service.detect_pii(df).keys()),
    )


@app.route('/api/stats')
def api_stats():
    df = load_dataframe(max_rows=app.config['MAX_PREVIEW_ROWS'])
    if df is None:
        return jsonify(error='No file uploaded'), 404
    return jsonify(stats=csv_service.get_summary_stats(df))


@app.route('/api/builder/data', methods=['POST'])
def api_builder_data():
    """Return column data for the chart builder."""
    df = load_dataframe(max_rows=app.config['MAX_PREVIEW_ROWS'])
    if df is None:
        return jsonify(error='No file uploaded'), 404

    spec = request.get_json() or {}
    x_col = spec.get('x')
    y_col = spec.get('y')
    color_col = spec.get('color')
    agg = spec.get('agg', 'none')

    result = {'x_col': x_col, 'y_col': y_col}

    needed = [c for c in [x_col, y_col, color_col] if c and c in df.columns]
    if not needed:
        return jsonify(error='No valid columns selected'), 400

    subset = df[needed].dropna().head(5000)

    if agg != 'none' and x_col and y_col and x_col in df.columns and y_col in df.columns:
        grouped = df.groupby(x_col)[y_col]
        agg_map = {'mean': 'mean', 'sum': 'sum', 'count': 'count',
                    'median': 'median', 'min': 'min', 'max': 'max'}
        if agg in agg_map:
            agg_result = getattr(grouped, agg_map[agg])().sort_values(ascending=False).head(50)
            result['x'] = agg_result.index.astype(str).tolist()
            result['y'] = agg_result.values.tolist()
            result['aggregated'] = True
    else:
        if x_col and x_col in subset.columns:
            result['x'] = subset[x_col].astype(str).tolist() if not pd.api.types.is_numeric_dtype(subset[x_col]) else subset[x_col].tolist()
        if y_col and y_col in subset.columns:
            result['y'] = subset[y_col].tolist()
        if color_col and color_col in subset.columns:
            result['color'] = subset[color_col].astype(str).tolist()

    return jsonify(result)


@app.route('/api/csv/raw')
def api_csv_raw():
    """Serve the raw CSV file for client-side processing (DuckDB-WASM)."""
    path = get_upload_path()
    if not path:
        return jsonify(error='No file uploaded'), 404
    return send_file(path, mimetype='text/csv')


@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json()
    if not data or 'question' not in data:
        return jsonify(error='Missing question'), 400

    df = load_dataframe(max_rows=app.config['MAX_CHAT_ROWS'])
    if df is None:
        return jsonify(error='No file uploaded'), 404

    col_info = csv_service.get_column_info(df)
    result = llm_service.chat_with_data(
        question=data['question'],
        df=df,
        ollama_url=app.config['OLLAMA_BASE_URL'],
        model=app.config['OLLAMA_MODEL'],
        column_info=col_info,
    )
    return jsonify(result)


@app.route('/api/ollama/status')
def api_ollama_status():
    status = llm_service.check_ollama_health(app.config['OLLAMA_BASE_URL'])
    return jsonify(status)


# ---------------------------------------------------------------------------
# Background Analysis API
# ---------------------------------------------------------------------------

def _session_key():
    """Return a stable key for this session's analysis tasks."""
    return session.get('upload_path', '')


@app.route('/api/analysis/start', methods=['POST'])
def api_analysis_start():
    """Kick off background analysis tasks. Returns immediately."""
    path = get_upload_path()
    if not path:
        return jsonify(error='No file uploaded'), 404

    key = _session_key()
    clear_session(key)  # Fresh analysis for each start

    max_rows = app.config['MAX_PREVIEW_ROWS']

    def run_insights():
        df = csv_service.parse_csv(path, nrows=max_rows)
        return csv_service.generate_insights(df)

    def run_charts():
        df = csv_service.parse_csv(path, nrows=max_rows)
        col_info = csv_service.get_column_info(df)
        return csv_service.suggest_charts(df, col_info)

    def run_stats():
        df = csv_service.parse_csv(path, nrows=max_rows)
        return csv_service.get_summary_stats(df)

    def run_pii():
        df = csv_service.parse_csv(path, nrows=max_rows)
        pii = csv_service.detect_pii(df)
        return {'pii': pii, 'has_pii': len(pii) > 0}

    start_analysis(key, 'insights', run_insights)
    start_analysis(key, 'charts', run_charts)
    start_analysis(key, 'stats', run_stats)
    start_analysis(key, 'pii', run_pii)

    return jsonify(success=True, tasks=['insights', 'charts', 'stats', 'pii'])


@app.route('/api/analysis/status')
def api_analysis_status():
    """Poll for background analysis results."""
    key = _session_key()
    return jsonify(get_all_status(key))


# ---------------------------------------------------------------------------
# Dashboard Persistence API
# ---------------------------------------------------------------------------

def _dashboard_path(dash_id):
    """Return safe path for a dashboard JSON file."""
    safe_id = secure_filename(dash_id)
    if not safe_id:
        return None
    path = os.path.join(app.config['DASHBOARD_FOLDER'], f'{safe_id}.json')
    real_path = os.path.realpath(path)
    real_folder = os.path.realpath(app.config['DASHBOARD_FOLDER'])
    if not real_path.startswith(real_folder + os.sep):
        return None
    return path


@app.route('/api/dashboards', methods=['GET'])
def api_dashboards_list():
    """List all saved dashboards."""
    folder = app.config['DASHBOARD_FOLDER']
    dashboards = []
    for fname in sorted(os.listdir(folder)):
        if not fname.endswith('.json'):
            continue
        try:
            with open(os.path.join(folder, fname)) as f:
                data = json.load(f)
            dashboards.append({
                'id': data.get('id', fname[:-5]),
                'name': data.get('name', 'Untitled'),
                'widget_count': len(data.get('widgets', [])),
                'created_at': data.get('created_at'),
                'updated_at': data.get('updated_at'),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return jsonify(dashboards=dashboards)


@app.route('/api/dashboards', methods=['POST'])
def api_dashboards_save():
    """Save a new or updated dashboard."""
    spec = request.get_json()
    if not spec or not spec.get('name'):
        return jsonify(error='Dashboard name required'), 400

    dash_id = spec.get('id') or uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()

    dashboard = {
        'id': dash_id,
        'name': spec['name'],
        'widgets': spec.get('widgets', []),
        'created_at': spec.get('created_at', now),
        'updated_at': now,
    }

    path = _dashboard_path(dash_id)
    if not path:
        return jsonify(error='Invalid dashboard ID'), 400

    with open(path, 'w') as f:
        json.dump(dashboard, f, indent=2)

    return jsonify(success=True, id=dash_id, dashboard=dashboard)


@app.route('/api/dashboards/<dash_id>')
def api_dashboards_get(dash_id):
    """Load a saved dashboard."""
    path = _dashboard_path(dash_id)
    if not path or not os.path.isfile(path):
        return jsonify(error='Dashboard not found'), 404
    with open(path) as f:
        return jsonify(json.load(f))


@app.route('/api/dashboards/<dash_id>', methods=['DELETE'])
def api_dashboards_delete(dash_id):
    """Delete a saved dashboard."""
    path = _dashboard_path(dash_id)
    if not path or not os.path.isfile(path):
        return jsonify(error='Dashboard not found'), 404
    os.remove(path)
    return jsonify(success=True)


# ---------------------------------------------------------------------------
# Vector Search API (Oracle AI — optional)
# ---------------------------------------------------------------------------

@app.route('/api/memory/status')
def api_memory_status():
    """Check if Oracle Vector Search is available."""
    available = vector_service.is_available(app.config)
    return jsonify(available=available)


@app.route('/api/memory/search')
def api_memory_search():
    """Semantic search across stored datasets."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify(error='Query parameter q required'), 400
    results = vector_service.search_datasets(app.config, query, limit=10)
    return jsonify(results=results)


@app.route('/api/memory/recent')
def api_memory_recent():
    """List recently uploaded datasets."""
    results = vector_service.list_recent(app.config, limit=20)
    return jsonify(results=results)


# ---------------------------------------------------------------------------
# Plugin API
# ---------------------------------------------------------------------------

@app.route('/api/plugins')
def api_plugins_list():
    """List all registered plugins."""
    return jsonify(
        plugins=plugin_service.get_plugins(),
        hook_types=plugin_service.get_hook_types(),
    )


@app.route('/api/plugins/<name>/toggle', methods=['POST'])
def api_plugins_toggle(name):
    """Enable or disable a plugin."""
    plugins = {p['name']: p for p in plugin_service.get_plugins()}
    if name not in plugins:
        return jsonify(error='Plugin not found'), 404
    plugin = plugin_service._plugins[name]
    plugin.enabled = not plugin.enabled
    return jsonify(name=name, enabled=plugin.enabled)


# ---------------------------------------------------------------------------
# Collaboration API (REST endpoints, always available)
# ---------------------------------------------------------------------------

@app.route('/api/collab/create', methods=['POST'])
def api_collab_create():
    """Create a new collaboration room."""
    data = request.get_json() or {}
    name = data.get('name', 'Anonymous')
    room_id = collab_service.create_room(creator_name=name)
    return jsonify(room_id=room_id, websocket=HAS_SOCKETIO)


@app.route('/api/collab/<room_id>/info')
def api_collab_info(room_id):
    """Get room info and participants."""
    if not collab_service.room_exists(room_id):
        return jsonify(error='Room not found'), 404
    participants = collab_service.get_participants(room_id)
    return jsonify(room_id=room_id, participants=participants, websocket=HAS_SOCKETIO)


# ---------------------------------------------------------------------------
# WebSocket events (only if flask-socketio is installed)
# ---------------------------------------------------------------------------

socketio = None
if HAS_SOCKETIO:
    socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

    @socketio.on('join')
    def on_join(data):
        room_id = data.get('room')
        name = data.get('name', 'Anonymous')
        if not room_id:
            return

        # Auto-create room if needed
        if not collab_service.room_exists(room_id):
            collab_service.create_room(creator_name=name)

        participant = collab_service.join_room(room_id, request.sid, name)
        if not participant:
            return

        sio_join(room_id)
        emit('user_joined', {
            'name': name,
            'color': participant.color,
            'participants': collab_service.get_participants(room_id),
        }, to=room_id)

    @socketio.on('leave')
    def on_leave(data):
        room_id = data.get('room')
        if not room_id:
            return
        collab_service.leave_room(room_id, request.sid)
        sio_leave(room_id)
        emit('user_left', {
            'sid': request.sid,
            'participants': collab_service.get_participants(room_id),
        }, to=room_id)

    @socketio.on('disconnect')
    def on_disconnect():
        # Clean up from all rooms
        for room_id in list(collab_service._rooms.keys()):
            room = collab_service.get_room(room_id)
            if room and request.sid in room.participants:
                collab_service.leave_room(room_id, request.sid)
                emit('user_left', {
                    'sid': request.sid,
                    'participants': collab_service.get_participants(room_id),
                }, to=room_id)

    @socketio.on('cursor_move')
    def on_cursor_move(data):
        """Broadcast cursor position to other users in the room."""
        room_id = data.get('room')
        if not room_id:
            return
        emit('cursor_update', {
            'sid': request.sid,
            'tab': data.get('tab'),
            'x': data.get('x'),
            'y': data.get('y'),
        }, to=room_id, include_self=False)

    @socketio.on('tab_change')
    def on_tab_change(data):
        """Notify room when someone changes tabs."""
        room_id = data.get('room')
        if not room_id:
            return
        emit('tab_changed', {
            'sid': request.sid,
            'tab': data.get('tab'),
        }, to=room_id, include_self=False)

    @socketio.on('chart_shared')
    def on_chart_shared(data):
        """Share a chart configuration with the room."""
        room_id = data.get('room')
        if not room_id:
            return
        emit('chart_received', {
            'sid': request.sid,
            'chart': data.get('chart'),
        }, to=room_id, include_self=False)

    @socketio.on('chat_message')
    def on_chat_message(data):
        """Broadcast a chat message to the room."""
        room_id = data.get('room')
        if not room_id:
            return
        room = collab_service.get_room(room_id)
        participant = room.participants.get(request.sid) if room else None
        emit('chat_broadcast', {
            'sid': request.sid,
            'name': participant.name if participant else 'Anonymous',
            'color': participant.color if participant else '#666',
            'message': data.get('message', ''),
        }, to=room_id)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if socketio:
        socketio.run(app, debug=True, port=5000)
    else:
        app.run(debug=True, port=5000)
