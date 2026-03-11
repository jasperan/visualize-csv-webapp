import glob
import logging
import os
import uuid

import pandas as pd
from flask import (Flask, request, render_template, session,
                   redirect, url_for, jsonify)
from werkzeug.utils import secure_filename

from config import Config
from services import csv_service, llm_service

app = Flask(__name__)
app.config.from_object(Config)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
    return jsonify(insights=csv_service.generate_insights(df))


@app.route('/api/charts')
def api_charts():
    df = load_dataframe(max_rows=app.config['MAX_PREVIEW_ROWS'])
    if df is None:
        return jsonify(error='No file uploaded'), 404
    col_info = csv_service.get_column_info(df)
    charts = csv_service.suggest_charts(df, col_info)
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
# Run
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    app.run(debug=True, port=5000)
