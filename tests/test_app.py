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

    def test_data_server_side_sort(self, uploaded_client):
        resp = uploaded_client.get('/api/data?sort=age&sort_asc=true&per_page=3')
        data = resp.get_json()
        ages = [r[1] for r in data['rows']]  # age is column index 1
        assert ages == sorted(ages)

    def test_data_per_page_lower_bound(self, uploaded_client):
        resp = uploaded_client.get('/api/data?per_page=0')
        data = resp.get_json()
        assert data['per_page'] == 1  # clamped to 1

    def test_data_404_without_upload(self, client):
        resp = client.get('/api/data')
        assert resp.status_code == 404


class TestPathTraversal:
    def test_session_path_traversal_blocked(self, client):
        with client.session_transaction() as sess:
            sess['upload_path'] = '/etc/passwd'
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


class TestAPIPII:
    def test_pii_detection_no_pii(self, uploaded_client):
        resp = uploaded_client.get('/api/pii')
        assert resp.status_code == 200
        data = resp.get_json()
        # Sample data has no PII (names but not emails/SSNs)
        assert isinstance(data['pii'], dict)

    def test_pii_redact_endpoint(self, uploaded_client):
        resp = uploaded_client.post('/api/pii/redact',
            json={}, content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'columns' in data
        assert 'rows' in data


class TestAPIRawCSV:
    def test_raw_csv_returns_file(self, uploaded_client):
        resp = uploaded_client.get('/api/csv/raw')
        assert resp.status_code == 200
        assert b'name,age,salary,department' in resp.data
        assert b'Alice' in resp.data

    def test_raw_csv_404_without_upload(self, client):
        resp = client.get('/api/csv/raw')
        assert resp.status_code == 404


class TestAPIBuilder:
    def test_builder_data(self, uploaded_client):
        resp = uploaded_client.post('/api/builder/data',
            json={'x': 'department', 'y': 'salary', 'agg': 'mean'},
            content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'x' in data
        assert 'y' in data
        assert data['aggregated'] is True

    def test_builder_data_no_agg(self, uploaded_client):
        resp = uploaded_client.post('/api/builder/data',
            json={'x': 'age', 'y': 'salary', 'agg': 'none'},
            content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['x']) == 10  # All 10 rows

    def test_builder_no_columns(self, uploaded_client):
        resp = uploaded_client.post('/api/builder/data',
            json={}, content_type='application/json')
        assert resp.status_code == 400


class TestAsyncAnalysis:
    def test_analysis_start_and_poll(self, uploaded_client):
        import time
        resp = uploaded_client.post('/api/analysis/start')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'insights' in data['tasks']

        # Poll until done (should be fast with 10-row CSV)
        for _ in range(20):
            resp = uploaded_client.get('/api/analysis/status')
            status = resp.get_json()
            if all(t.get('status') == 'done' for t in status.values()):
                break
            time.sleep(0.1)

        assert status['insights']['status'] == 'done'
        assert status['charts']['status'] == 'done'
        assert status['stats']['status'] == 'done'
        assert status['pii']['status'] == 'done'
        assert isinstance(status['insights']['result'], list)

    def test_analysis_404_without_upload(self, client):
        resp = client.post('/api/analysis/start')
        assert resp.status_code == 404


class TestDashboards:
    def test_create_and_list_dashboard(self, client, tmp_path):
        # Configure dashboard folder
        client.application.config['DASHBOARD_FOLDER'] = str(tmp_path / 'dashboards')
        import os
        os.makedirs(client.application.config['DASHBOARD_FOLDER'], exist_ok=True)

        resp = client.post('/api/dashboards',
            json={'name': 'Test Dashboard', 'widgets': [{'chartType': 'bar', 'x': 'col1'}]},
            content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        dash_id = data['id']

        # List
        resp = client.get('/api/dashboards')
        data = resp.get_json()
        assert len(data['dashboards']) == 1
        assert data['dashboards'][0]['name'] == 'Test Dashboard'

        # Get
        resp = client.get(f'/api/dashboards/{dash_id}')
        data = resp.get_json()
        assert data['name'] == 'Test Dashboard'
        assert len(data['widgets']) == 1

        # Delete
        resp = client.delete(f'/api/dashboards/{dash_id}')
        assert resp.status_code == 200
        resp = client.get(f'/api/dashboards/{dash_id}')
        assert resp.status_code == 404

    def test_dashboard_requires_name(self, client):
        resp = client.post('/api/dashboards',
            json={}, content_type='application/json')
        assert resp.status_code == 400

    def test_dashboard_not_found(self, client, tmp_path):
        client.application.config['DASHBOARD_FOLDER'] = str(tmp_path / 'dashboards')
        import os
        os.makedirs(client.application.config['DASHBOARD_FOLDER'], exist_ok=True)
        resp = client.get('/api/dashboards/nonexistent')
        assert resp.status_code == 404


class TestVectorMemory:
    def test_memory_status_without_oracle(self, client):
        resp = client.get('/api/memory/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['available'] is False  # No Oracle configured in test

    def test_memory_search_without_oracle(self, client):
        resp = client.get('/api/memory/search?q=sales+data')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['results'] == []

    def test_memory_recent_without_oracle(self, client):
        resp = client.get('/api/memory/recent')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['results'] == []

    def test_memory_search_requires_query(self, client):
        resp = client.get('/api/memory/search')
        assert resp.status_code == 400


class TestCollaboration:
    def test_create_room(self, client):
        resp = client.post('/api/collab/create',
            json={'name': 'Alice'}, content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'room_id' in data
        assert len(data['room_id']) == 8

    def test_room_info(self, client):
        # Create a room first
        resp = client.post('/api/collab/create',
            json={'name': 'Alice'}, content_type='application/json')
        room_id = resp.get_json()['room_id']

        # Get info
        resp = client.get(f'/api/collab/{room_id}/info')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['room_id'] == room_id

    def test_room_not_found(self, client):
        resp = client.get('/api/collab/nonexistent/info')
        assert resp.status_code == 404


class TestCollabService:
    def test_room_lifecycle(self):
        from services.collab_service import create_room, join_room, leave_room, get_participants, room_exists
        room_id = create_room('Alice')
        assert room_exists(room_id)

        p = join_room(room_id, 'sid1', 'Alice')
        assert p is not None
        assert p.name == 'Alice'

        participants = get_participants(room_id)
        assert len(participants) == 1

        leave_room(room_id, 'sid1')
        # Room auto-cleans when empty
        assert not room_exists(room_id)


class TestPlugins:
    def test_list_plugins(self, client):
        resp = client.get('/api/plugins')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'plugins' in data
        assert 'hook_types' in data
        assert isinstance(data['plugins'], list)

    def test_plugin_service_registration(self):
        from services.plugin_service import Plugin, register_plugin, unregister_plugin, get_plugins, run_hooks

        def my_insight(df):
            return [{'type': 'test', 'title': 'Test insight'}]

        plugin = Plugin(
            name='test-plugin',
            version='0.1.0',
            hooks={'insight_generator': my_insight},
        )
        assert register_plugin(plugin)
        assert any(p['name'] == 'test-plugin' for p in get_plugins())

        # Run the hook
        import pandas as pd
        results = run_hooks('insight_generator', pd.DataFrame({'a': [1, 2]}))
        assert len(results) >= 1
        test_result = [r for r in results if r['plugin'] == 'test-plugin']
        assert len(test_result) == 1
        assert test_result[0]['result'][0]['title'] == 'Test insight'

        # Cleanup
        unregister_plugin('test-plugin')
        assert not any(p['name'] == 'test-plugin' for p in get_plugins())

    def test_example_plugin_loads(self):
        from services.plugin_service import get_plugins
        names = [p['name'] for p in get_plugins()]
        assert 'data-quality' in names


class TestPIIService:
    def test_detect_pii_with_emails(self, tmp_path):
        from services.csv_service import parse_csv, detect_pii
        csv = tmp_path / 'pii.csv'
        csv.write_text(
            'name,email,phone\n'
            'Alice,alice@example.com,555-123-4567\n'
            'Bob,bob@test.org,555-987-6543\n'
        )
        df = parse_csv(str(csv))
        pii = detect_pii(df)
        assert 'email' in pii
        assert any(p['type'] == 'email' for p in pii['email'])

    def test_redact_pii(self, tmp_path):
        from services.csv_service import parse_csv, redact_pii
        csv = tmp_path / 'pii.csv'
        csv.write_text(
            'name,email\n'
            'Alice,alice@example.com\n'
            'Bob,bob@test.org\n'
        )
        df = parse_csv(str(csv))
        redacted = redact_pii(df)
        assert '***@***.***' in redacted['email'].iloc[0]


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
