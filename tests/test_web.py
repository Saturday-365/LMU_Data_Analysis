"""HTTP integration tests against real synthetic DuckDB files and local persistence."""
from codecs import BOM_UTF8
import csv
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb
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
        fixture(self.source, end_s=60)
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
            with patch('lmu_data_analysis.web_service.read_recording', side_effect=AssertionError('duplicate was parsed')):
                duplicate = self.upload(restarted, **{'x-filename':'renamed.duckdb'})
            self.assertEqual(duplicate.status_code, 409)
            self.assertEqual(duplicate.json()['code'], 'duplicate')
            self.assertEqual(restarted.get(url).json(), trace)
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

    def test_saved_intervals_stay_in_owner_and_layout_across_restart(self):
        with duckdb.connect(str(self.source)) as connection:
            connection.execute("INSERT INTO metadata VALUES ('TrackName', 'Synthetic test track')")
        headers = {'x-lmu-client': 'web'}
        with TestClient(create_app(self.data, identity=TestIdentity())) as client:
            payload = self.source.read_bytes()
            first = self.upload(client, content=payload).json()['session']['id']
            outsider = self.upload(client, content=payload, **{'x-test-owner':'driver-b'}).json()['session']['id']
            with duckdb.connect(str(self.source)) as connection:
                connection.execute("INSERT INTO metadata VALUES ('CarName', 'Another vehicle')")
            second = self.upload(client, content=self.source.read_bytes()).json()['session']['id']
            with duckdb.connect(str(self.source)) as connection:
                connection.execute("UPDATE metadata SET value='Other layout' WHERE key='TrackLayout'")
            other_layout = self.upload(client, content=self.source.read_bytes()).json()['session']['id']
            url = f'/api/v1/sessions/{first}/intervals'
            response = client.post(url, json={'name':' 第一弯 ', 'start_m':21, 'end_m':53.5}, headers=headers)
            self.assertEqual(response.status_code, 201, response.text)
            saved = response.json()
            self.assertEqual(saved['name'], '第一弯')
            item_url = f'/api/v1/sessions/{second}/intervals'
            self.assertEqual(client.get(item_url).json()['items'], [saved])
            self.assertEqual(client.get(f'/api/v1/sessions/{other_layout}/intervals').json()['items'], [])
            foreign = f'/api/v1/sessions/{outsider}/intervals'
            self.assertEqual(client.get(url, headers={'x-test-owner':'driver-b'}).status_code, 404)
            self.assertEqual(client.delete(f"{foreign}/{saved['id']}", headers={
                **headers, 'x-test-owner':'driver-b'}).status_code, 404)
            self.assertEqual(client.post(url, json={'name':'第一弯','start_m':22,'end_m':36}, headers=headers).status_code, 409)
            self.assertEqual(client.post(url, json={'name':'无效','start_m':40,'end_m':30}, headers=headers).status_code, 422)
            changed = client.put(f"{item_url}/{saved['id']}",
                                 json={'name':'第一弯入口','start_m':26,'end_m':36}, headers=headers)
            self.assertEqual(changed.status_code, 200, changed.text)
        with TestClient(create_app(self.data, identity=TestIdentity())) as restarted:
            self.assertEqual(restarted.get(url).json()['items'], [changed.json()])
            self.assertEqual(restarted.delete(f"{url}/{saved['id']}", headers=headers).status_code, 200)
            self.assertEqual(restarted.get(item_url).json()['items'], [])

    def test_archive_pace_and_manual_vehicle_model(self):
        session = self.upload().json()['session']
        base = f"/api/v1/sessions/{session['id']}"
        response = self.client.patch(base + '/conditions', headers={'x-lmu-client':'web'},
                                     json={'changes':{'model':{'state':'known', 'value':'测试车型'}}})
        self.assertEqual(response.status_code, 200, response.text)
        latest = self.client.get('/api/v1/sessions').json()['items'][0]
        self.assertEqual(latest['vehicle_model'], '测试车型')
        response = self.client.patch(base + '/conditions', headers={'x-lmu-client':'web'},
                                     json={'changes':{'brand':{'state':'known', 'value':'法拉利'}}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get('/api/v1/sessions').json()['items'][0]['vehicle_brand'], 'Ferrari')
        self.assertEqual(latest['pace'], {'count':2, 'best_s':10, 'best_ordinal':1, 'median_s':10, 'stddev_s':0})

    def test_archive_csv_exports_owned_laps_and_preserves_missing_times(self):
        with duckdb.connect(str(self.source)) as connection:
            connection.executemany('INSERT INTO metadata VALUES (?, ?)', [
                ('TrackName', '=Monza, test'), ('RecordingTime', '2026-11-21T20_23_11+08_00'),
                ('SessionType', 'Qualifying'), ('CarClass', 'GT3')])
            connection.execute('INSERT INTO "In Pits" VALUES (20, 1)')
            connection.execute('DELETE FROM "Lap Time" WHERE ts=25')
        payload = self.source.read_bytes()
        url = '/api/v1/archive/laps.csv'
        with TestClient(create_app(self.data, identity=TestIdentity())) as client:
            def csv_rows(response):
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.content.startswith(BOM_UTF8))
                return list(csv.DictReader(StringIO(response.content.decode('utf-8-sig'), newline='')))

            self.assertEqual(csv_rows(client.get(url)), [])
            self.upload(client, content=payload, **{'x-test-owner':'another-owner', 'x-filename':'other.duckdb'})
            saved = self.upload(client, content=payload).json()['session']
            edited = client.patch(f"/api/v1/sessions/{saved['id']}/conditions", headers={'x-lmu-client':'web'},
                                  json={'changes':{'brand':{'state':'known','value':'法拉利'},
                                                   'model':{'state':'known','value':'车型, GT3'}}})
            self.assertEqual(edited.status_code, 200, edited.text)
            with patch('lmu_data_analysis.web_service.read_recording', side_effect=AssertionError('export reopened telemetry')):
                response = client.get(url)
            self.assertEqual(response.headers['content-disposition'], 'attachment; filename="LMU-Lap-Archive.csv"')
            first, second = csv_rows(response)
            self.assertEqual(first['会话编号'], saved['id'])
            self.assertEqual(first['录制文件'], 'sample.duckdb')
            self.assertEqual(first['录制时间（UTC）'], '2026-11-21T12:23:11+00:00')
            self.assertEqual(first['赛道'], "'=Monza, test")
            self.assertEqual((first['会话类型'], first['品牌'], first['车型']), ('排位', 'Ferrari', '车型, GT3'))
            self.assertEqual((first['源圈号'], first['官方圈时（秒）'], first['纳入节奏统计']), ('1','10.000','是'))
            self.assertEqual((second['官方圈时（秒）'], second['记录到进站状态'], second['纳入节奏统计']), ('','是','否'))
            self.assertNotIn('PRIVATE_TEST', response.content.decode('utf-8-sig'))

    def test_compare_across_sessions_checks_layout_ownership_and_delta(self):
        with duckdb.connect(str(self.source)) as connection:
            connection.execute("INSERT INTO metadata VALUES ('TrackName', 'Synthetic test track')")
        with TestClient(create_app(self.data, identity=TestIdentity())) as client:
            first = self.upload(client, content=self.source.read_bytes()).json()['session']
            with duckdb.connect(str(self.source)) as connection:
                connection.execute("INSERT INTO metadata VALUES ('CarName', 'Different car')")
            same_layout = self.upload(client, content=self.source.read_bytes()).json()['session']
            other_driver = self.upload(client, content=self.source.read_bytes(),
                                       **{'x-test-owner':'driver-b'}).json()['session']
            with duckdb.connect(str(self.source)) as connection:
                connection.execute("UPDATE metadata SET value='Different layout' WHERE key='TrackLayout'")
            other_layout = self.upload(client, content=self.source.read_bytes()).json()['session']
            url = f"/api/v1/sessions/{first['id']}/laps/{first['laps'][0]['id']}/comparison"

            def compare(reference):
                return client.get(url, params={'reference_session_id':reference['id'],
                                               'reference_lap_id':reference['laps'][0]['id']})

            result = compare(same_layout)
            self.assertEqual(result.status_code, 200, result.text)
            delta = result.json()['delta']
            self.assertTrue(delta['comparable'])
            self.assertTrue(delta['values'])
            self.assertTrue(all(value == 0 for value in delta['values'] if value is not None))
            self.assertEqual(compare(other_driver).status_code, 404)
            self.assertEqual(compare(other_layout).status_code, 422)

    def test_trace_with_gps_and_invalid_optional_coordinate_unit(self):
        with duckdb.connect(str(self.source)) as c:
            for name, expression in [('GPS Latitude','60+sin(i/100.0)*0.001'),('GPS Longitude','cos(i/100.0)*0.002')]:
                c.execute('INSERT INTO channelsList VALUES (?,10,?)',[name,'deg'])
                c.execute(f'CREATE TABLE "{name}" AS SELECT {expression} AS value FROM range(601) t(i)')
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
            pace = client.get(base+'/pace').json()
            self.assertEqual(pace['statistics']['count'], 2)
            self.assertEqual(pace['stints'][0]['start_kind'], 'pit_exit')
            self.assertEqual(pace['stints'][0]['lap_ordinals'], [1, 2])
            for endpoint in ('timing','inventory','pace'):
                self.assertEqual(client.get(base+'/'+endpoint,headers={'x-test-owner':'driver-b'}).status_code,404)
        # Derived endpoints re-read existing blobs; no catalog migration or re-import required.
        with TestClient(create_app(self.data, identity=TestIdentity())) as restarted:
            self.assertEqual(restarted.get(base+'/timing').json(),timing)

    def test_wrong_sector_unit_does_not_break_core_import(self):
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

    def test_import_requires_one_minute_and_one_complete_lap(self):
        short = self.folder/'short.duckdb'
        fixture(short, end_s=59.99)
        response = self.upload(content=short.read_bytes())
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['code'], 'recording_too_short')

        with duckdb.connect(str(self.source)) as connection:
            connection.execute('DELETE FROM "Lap" WHERE value >= 2')
        response = self.upload(content=self.source.read_bytes())
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['code'], 'no_complete_lap')
        self.assertEqual(self.client.get('/api/v1/sessions').json()['items'], [])
        self.assertEqual(list((self.data/'recordings').iterdir()), [])

        with duckdb.connect(str(self.source)) as connection:
            connection.execute('INSERT INTO "Lap" VALUES (15, 2)')
        response = self.upload(content=self.source.read_bytes())
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['session']['duration_s'], 60)
        self.assertEqual(response.json()['session']['complete_lap_count'], 1)

    def test_conflict_at_insert_also_rejects_and_removes_new_blob(self):
        self.assertEqual(self.upload().status_code, 201)
        with patch.object(self.app.state.service.repository, 'find_hash', return_value=None):
            response = self.upload()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'duplicate')
        self.assertEqual(len(self.client.get('/api/v1/sessions').json()['items']), 1)
        self.assertEqual(len(list((self.data/'recordings').iterdir())), 1)

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
