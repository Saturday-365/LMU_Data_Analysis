"""HTTP integration tests against real synthetic DuckDB files and local persistence."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from test_reader import ROOT, fixture
from lmu_data_analysis.web_app import create_app, LOCAL_DRIVER_ID


class TestIdentity:
    def current_driver(self, request):
        return request.headers.get('x-test-owner', 'driver-a')


class WebTests(unittest.TestCase):
    def setUp(self):
        self.output_root = (ROOT / 'outputs').resolve()
        self.output_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='web-test-', dir=self.output_root)
        self.folder = Path(self.temp.name).resolve()
        self.addCleanup(self.cleanup)
        self.source = self.folder / 'sample.duckdb'
        fixture(self.source)
        self.payload = self.source.read_bytes()
        self.data = self.folder / 'data'
        self.app = create_app(self.data)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def cleanup(self):
        if self.folder.parent != self.output_root or not self.folder.name.startswith('web-test-'):
            raise RuntimeError('Unexpected cleanup target')
        self.temp.cleanup()

    def upload(self, client=None, content=None, **headers):
        return (client or self.client).post('/api/v1/sessions', content=self.payload if content is None else content,
            headers={'x-lmu-client':'web','x-filename':'sample.duckdb',**headers})

    def test_import_trace_restart_and_deduplicate(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.text)
        session = response.json()['session']
        self.assertEqual(session['complete_lap_count'], 2)
        self.assertEqual(session['laps'][0]['display_time'], '0:10.000')
        self.assertNotIn('blob_key', session)
        self.assertNotIn('DriverName', session['metadata'])
        url = f"/api/v1/sessions/{session['id']}/laps/{session['laps'][0]['id']}/trace"
        trace = self.client.get(url).json()
        self.assertEqual(len(trace['time_s']), 1000)
        self.assertTrue(trace['distance_available'])
        self.assertEqual(trace['channels']['gear']['values'][0], 3)
        self.assertTrue(all(v is None or v == int(v) for v in trace['channels']['gear']['values']))
        self.assertEqual(self.payload, self.source.read_bytes())
        with TestClient(create_app(self.data)) as restarted:
            self.assertEqual(restarted.get('/api/v1/sessions').json()['items'][0]['id'], session['id'])
            self.assertEqual(restarted.get(url).json(), trace)
            duplicate = self.upload(restarted)
            self.assertEqual(duplicate.status_code, 200)
            self.assertTrue(duplicate.json()['duplicate'])
            self.assertEqual(duplicate.json()['session']['laps'], session['laps'])
        self.assertEqual(len(list((self.data/'recordings').glob('*.duckdb'))), 1)
        self.assertEqual(list((self.data/'recordings').glob('*.upload')), [])

    def test_owner_filtering_including_cached_trace(self):
        with TestClient(create_app(self.data, identity=TestIdentity())) as client:
            session = self.upload(client).json()['session']
            url = f"/api/v1/sessions/{session['id']}"
            trace_url = f"{url}/laps/{session['laps'][0]['id']}/trace"
            self.assertEqual(client.get(trace_url).status_code, 200)
            headers = {'x-test-owner':'driver-b'}
            self.assertEqual(client.get(url, headers=headers).status_code, 404)
            self.assertEqual(client.get(trace_url, headers=headers).status_code, 404)
            self.assertEqual(client.get('/api/v1/sessions', headers=headers).json()['items'], [])
            other = self.upload(client, **headers).json()['session']
            self.assertNotEqual(other['id'], session['id'])
            self.assertEqual(other['driver_id'], 'driver-b')
            self.assertEqual(client.get(f"{url}/laps/{other['laps'][0]['id']}/trace").status_code, 404)

    def test_local_identity_cannot_be_overridden(self):
        me = self.client.get('/api/v1/me', headers={'x-driver-id':'someone-else'}).json()
        self.assertEqual(me['id'], LOCAL_DRIVER_ID)

    def test_trace_with_gps_and_invalid_optional_coordinate_unit(self):
        import duckdb
        with duckdb.connect(str(self.source)) as c:
            for name, expression in [('GPS Latitude','60+sin(i/100.0)*0.001'),('GPS Longitude','cos(i/100.0)*0.002')]:
                c.execute('INSERT INTO channelsList VALUES (?,10,?)',[name,'deg'])
                c.execute(f'CREATE TABLE "{name}" AS SELECT {expression} AS value FROM range(300) t(i)')
        session=self.upload(content=self.source.read_bytes()).json()['session']
        url=f"/api/v1/sessions/{session['id']}/laps/{session['laps'][0]['id']}/trace"
        result=self.client.get(url).json()
        self.assertTrue(result['trajectory']['available'])
        self.assertEqual(len(result['trajectory']['points']),100)
        self.assertNotIn('latitude',result['channels'])
        with duckdb.connect(str(self.source)) as c:
            c.execute("UPDATE channelsList SET unit='rad' WHERE channelName='GPS Latitude'")
        other=self.upload(content=self.source.read_bytes()).json()['session']
        data=self.client.get(f"/api/v1/sessions/{other['id']}/laps/{other['laps'][0]['id']}/trace").json()
        self.assertFalse(data['trajectory']['available'])
        self.assertIn('speed',data['channels'])

    def test_timing_and_inventory_legacy_recordings_and_ownership(self):
        with TestClient(create_app(self.data, identity=TestIdentity())) as client:
            session = self.upload(client).json()['session']
            base = f"/api/v1/sessions/{session['id']}"
            timing = client.get(base+'/timing').json()
            self.assertEqual(timing['statistics']['count'],2)
            self.assertEqual(timing['statistics']['average_s'],10)
            self.assertIsNone(timing['statistics']['theoretical_s'])
            inv = client.get(base+'/inventory').json()
            self.assertEqual(inv['continuous_count'],6)
            self.assertNotIn('PRIVATE_TEST',str(inv))
            for endpoint in ('timing','inventory'):
                self.assertEqual(client.get(base+'/'+endpoint,headers={'x-test-owner':'driver-b'}).status_code,404)
        # Derived endpoints re-read existing blobs; no catalog migration or re-import required.
        with TestClient(create_app(self.data, identity=TestIdentity())) as restarted:
            self.assertEqual(restarted.get(base+'/timing').json(),timing)

    def test_wrong_sector_unit_does_not_break_core_import(self):
        import duckdb
        with duckdb.connect(str(self.source)) as connection:
            connection.execute("INSERT INTO eventsList VALUES ('Last Sector1','ms')")
            connection.execute('CREATE TABLE "Last Sector1"(ts DOUBLE,value DOUBLE)')
            connection.execute('INSERT INTO "Last Sector1" VALUES (15,3000)')
        session = self.upload(content=self.source.read_bytes()).json()['session']
        self.assertEqual(session['complete_lap_count'],2)
        self.assertTrue(any(d['code']=='sector_event_unusable' for d in session['diagnostics']))

    def test_invalid_and_oversize_imports_leave_no_records(self):
        self.assertEqual(self.upload(content=b'').status_code, 400)
        self.assertEqual(self.upload(content=b'not a database').status_code, 422)
        self.assertEqual(self.upload(**{'x-filename':'bad.exe'}).status_code, 400)
        with TestClient(create_app(self.data, max_upload_bytes=16)) as limited:
            self.assertEqual(self.upload(limited, content=b'0'*17).status_code, 413)
        self.assertEqual(self.client.get('/api/v1/sessions').json()['items'], [])
        self.assertEqual(list((self.data/'recordings').iterdir()), [])

    def test_local_boundary_and_static_isolation(self):
        self.assertEqual(self.client.post('/api/v1/sessions', content=b'').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/me', headers={'origin':'https://example.com'}).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/me', headers={'host':'example.com'}).status_code, 403)
        self.assertEqual(self.client.get('/data/catalog.sqlite3').status_code, 404)
        self.assertEqual(self.client.get('/assets/../data/catalog.sqlite3').status_code, 404)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertIn("script-src 'self'", self.client.get('/').headers['content-security-policy'])
        self.assertEqual(self.client.get('/assets/app.js').status_code, 200)

    def test_filename_is_display_only(self):
        session = self.upload(**{'x-filename':'..%5C..%5Cescape.duckdb'}).json()['session']
        self.assertEqual(session['filename'], 'escape.duckdb')
        self.assertFalse((self.folder/'escape.duckdb').exists())
        self.assertEqual(len(list((self.data/'recordings').glob('*.duckdb'))), 1)

    def test_failed_database_insert_removes_new_blob(self):
        with patch.object(self.app.state.service.repository, 'insert_session', side_effect=OSError('disk full')):
            response = self.upload()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(list((self.data/'recordings').iterdir()), [])
        self.assertEqual(self.client.get('/api/v1/sessions').json()['items'], [])


if __name__ == '__main__':
    unittest.main()
