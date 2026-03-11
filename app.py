import os
import uuid
import json

import pandas as pd
from flask import (Flask, request, render_template, session,
                   redirect, url_for, jsonify, abort)
from werkzeug.utils import secure_filename

from config import Config
from services import csv_service, llm_service

app = Flask(__name__)
app.config.from_object(Config)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
    return path


def load_dataframe(max_rows=None):
    """Load the session's CSV into a DataFrame."""
    path = get_upload_path()
    if not path:
        return None
    return csv_service.parse_csv(path, nrows=max_rows)


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
    """Return paginated table data."""
    df = load_dataframe(max_rows=app.config['MAX_PREVIEW_ROWS'])
    if df is None:
        return jsonify(error='No file uploaded'), 404

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 200)

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


@app.route('/api/stats')
def api_stats():
    df = load_dataframe(max_rows=app.config['MAX_PREVIEW_ROWS'])
    if df is None:
        return jsonify(error='No file uploaded'), 404
    return jsonify(stats=csv_service.get_summary_stats(df))


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
