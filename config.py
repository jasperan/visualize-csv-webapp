import os
import secrets


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    ALLOWED_EXTENSIONS = {'csv', 'tsv'}
    MAX_PREVIEW_ROWS = 500
    MAX_CHAT_ROWS = 2000
    DASHBOARD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboards')
    OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
    OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'qwen3.5:latest')
