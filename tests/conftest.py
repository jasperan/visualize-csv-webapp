import os
import tempfile
import pytest
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app as flask_app


@pytest.fixture
def app(tmp_path):
    flask_app.config.update({
        'TESTING': True,
        'UPLOAD_FOLDER': str(tmp_path),
        'SECRET_KEY': 'test-secret',
    })
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sample_csv(tmp_path):
    """Create a sample CSV file for testing."""
    csv_path = tmp_path / 'test.csv'
    csv_path.write_text(
        'name,age,salary,department\n'
        'Alice,30,70000,Engineering\n'
        'Bob,25,55000,Marketing\n'
        'Charlie,35,80000,Engineering\n'
        'Diana,28,60000,Sales\n'
        'Eve,32,75000,Engineering\n'
        'Frank,45,90000,Marketing\n'
        'Grace,29,65000,Sales\n'
        'Hank,38,85000,Engineering\n'
        'Ivy,26,52000,Marketing\n'
        'Jack,33,72000,Sales\n'
    )
    return csv_path


@pytest.fixture
def uploaded_client(client, sample_csv):
    """Return a client with a CSV already uploaded."""
    with open(sample_csv, 'rb') as f:
        from io import BytesIO
        data = f.read()

    with client.session_transaction() as sess:
        pass

    resp = client.post('/upload', data={
        'file': (BytesIO(data), 'test.csv'),
    }, content_type='multipart/form-data')
    assert resp.status_code == 200
    return client
