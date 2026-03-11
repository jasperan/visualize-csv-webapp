import json
import os
import sys
from io import BytesIO

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestIndex:
    def test_index_renders(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        assert b'CSV' in resp.data

    def test_dashboard_redirects_without_upload(self, client):
        resp = client.get('/dashboard')
        assert resp.status_code == 302


class TestUpload:
    def test_upload_csv(self, client, sample_csv):
        with open(sample_csv, 'rb') as f:
            data = f.read()
        resp = client.post('/upload', data={
            'file': (BytesIO(data), 'test.csv'),
        }, content_type='multipart/form-data')
        assert resp.status_code == 200
        result = resp.get_json()
        assert result['success'] is True
        assert result['filename'] == 'test.csv'
        assert result['columns'] == 4

    def test_upload_rejects_non_csv(self, client):
        resp = client.post('/upload', data={
            'file': (BytesIO(b'not a csv'), 'test.txt'),
        }, content_type='multipart/form-data')
        assert resp.status_code == 400

    def test_upload_rejects_no_file(self, client):
        resp = client.post('/upload', data={}, content_type='multipart/form-data')
        assert resp.status_code == 400


class TestAPIData:
    def test_data_returns_rows(self, uploaded_client):
        resp = uploaded_client.get('/api/data')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'columns' in data
        assert 'rows' in data
        assert len(data['columns']) == 4
        assert len(data['rows']) == 10

    def test_data_pagination(self, uploaded_client):
        resp = uploaded_client.get('/api/data?page=1&per_page=3')
        data = resp.get_json()
        assert len(data['rows']) == 3
        assert data['total_rows'] == 10
        assert data['total_pages'] == 4

    def test_data_404_without_upload(self, client):
        resp = client.get('/api/data')
        assert resp.status_code == 404


class TestAPIInsights:
    def test_insights_returns_list(self, uploaded_client):
        resp = uploaded_client.get('/api/insights')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'insights' in data
        assert isinstance(data['insights'], list)
        assert len(data['insights']) > 0
        # Should at least have the overview insight
        types = [i['type'] for i in data['insights']]
        assert 'overview' in types


class TestAPICharts:
    def test_charts_returns_list(self, uploaded_client):
        resp = uploaded_client.get('/api/charts')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'charts' in data
        assert isinstance(data['charts'], list)
        assert len(data['charts']) > 0

    def test_chart_types(self, uploaded_client):
        resp = uploaded_client.get('/api/charts')
        data = resp.get_json()
        chart_types = {c['type'] for c in data['charts']}
        # Sample data has numeric + categorical columns, so we should get histogram and bar at least
        assert 'histogram' in chart_types or 'bar' in chart_types


class TestAPIStats:
    def test_stats_returns_dict(self, uploaded_client):
        resp = uploaded_client.get('/api/stats')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'stats' in data
        assert 'age' in data['stats']
        assert data['stats']['age']['mean'] is not None


class TestAPIColumnInfo:
    def test_column_info(self, uploaded_client):
        resp = uploaded_client.get('/api/column_info')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'columns' in data
        names = [c['name'] for c in data['columns']]
        assert 'name' in names
        assert 'age' in names
        # age should be numeric
        age_col = next(c for c in data['columns'] if c['name'] == 'age')
        assert age_col['col_type'] == 'numeric'


class TestCSVService:
    def test_generate_insights(self, sample_csv):
        from services.csv_service import parse_csv, generate_insights
        df = parse_csv(str(sample_csv))
        insights = generate_insights(df)
        assert isinstance(insights, list)
        assert any(i['type'] == 'overview' for i in insights)

    def test_suggest_charts(self, sample_csv):
        from services.csv_service import parse_csv, get_column_info, suggest_charts
        df = parse_csv(str(sample_csv))
        col_info = get_column_info(df)
        charts = suggest_charts(df, col_info)
        assert isinstance(charts, list)
        assert len(charts) > 0

    def test_get_summary_stats(self, sample_csv):
        from services.csv_service import parse_csv, get_summary_stats
        df = parse_csv(str(sample_csv))
        stats = get_summary_stats(df)
        assert 'age' in stats
        assert stats['age']['mean'] == 32.1

    def test_column_type_detection(self, sample_csv):
        from services.csv_service import parse_csv, get_column_info
        df = parse_csv(str(sample_csv))
        info = get_column_info(df)
        info_dict = {c['name']: c for c in info}
        assert info_dict['age']['col_type'] == 'numeric'
        assert info_dict['department']['col_type'] == 'categorical'
