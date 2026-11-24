import os
from pathlib import Path
from shutil import copyfile
import tempfile
from time import monotonic, sleep
import unittest
from unittest.mock import patch

import duckdb
from fastapi.testclient import TestClient

from test_reader import ROOT, fixture
from lmu_data_analysis.reader import digest
from lmu_data_analysis.web_app import create_app


SETTINGS = '/api/v1/settings/auto-import'
CLIENT = {'x-lmu-client':'web'}


class AutoImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='auto-import-test-', dir=ROOT/'outputs')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'telemetry'
        self.source.mkdir()
        self.archive = self.root/'data'

    def wait_for_scan(self, client):
        deadline = monotonic() + 20
        while monotonic() < deadline:
            scan = client.get(SETTINGS).json()['scan']
            if scan['state'] == 'finished':
                return scan
            sleep(.04)
        self.fail('扫描未结束')

    def test_startup_imports_new_files_and_retries_recordings_with_wal(self):
        newest = self.source/'newest.duckdb'
        fixture(newest, end_s=60)
        duplicate = self.source/'renamed.DUCKDB'
        copyfile(newest, duplicate)
        short = self.source/'short.duckdb'
        fixture(short)
        future = self.source/'writing.duckdb'
        fixture(future, end_s=60)
        with duckdb.connect(str(future)) as connection:
            connection.execute("INSERT INTO metadata VALUES ('TrackName','Another race')")
        wal = self.source/'writing.duckdb.wal'
        wal.touch()
        subfolder = self.source/'elsewhere'
        subfolder.mkdir()
        copyfile(newest, subfolder/'ignored.duckdb')
        for index, path in enumerate([short, duplicate, newest, future], 1):
            os.utime(path, (1_700_000_000 + index, 1_700_000_000 + index))
        source_hash = digest(newest)

        with TestClient(create_app(self.archive)) as client:
            self.assertEqual(client.put(SETTINGS, json={'directory':str(self.source)}, headers=CLIENT).status_code, 200)
            self.assertEqual(client.get(SETTINGS).json()['scan']['state'], 'idle')

        app = create_app(self.archive)
        with patch.object(app.state.service, 'import_file', wraps=app.state.service.import_file) as importer:
            with TestClient(app) as client:
                scan = self.wait_for_scan(client)
                self.assertEqual((scan['total'], scan['imported'], scan['duplicate'], scan['filtered'], scan['deferred']),
                                 (4, 1, 1, 1, 1), scan)
                self.assertEqual([call.args[2] for call in importer.call_args_list],
                                 ['newest.duckdb', 'renamed.DUCKDB', 'short.duckdb'])
                self.assertEqual(len(client.get('/api/v1/sessions').json()['items']), 1)
        self.assertEqual(digest(newest), source_hash)
        self.assertFalse(list((self.archive/'recordings').glob('*.upload')))

        wal.unlink()
        with TestClient(create_app(self.archive)) as client:
            scan = self.wait_for_scan(client)
            self.assertEqual((scan['imported'], scan['unchanged'], scan['failed']), (1, 3, 0), scan)
            self.assertEqual(len(client.get('/api/v1/sessions').json()['items']), 2)
            self.assertEqual(client.post(SETTINGS+'/scan', headers=CLIENT).status_code, 202)
            self.assertEqual(self.wait_for_scan(client)['unchanged'], 4)

    def test_settings_validation_and_disabling(self):
        with TestClient(create_app(self.archive)) as client:
            self.assertEqual(client.post(SETTINGS+'/scan', headers=CLIENT).status_code, 422)
            for path in ('relative', str(self.root/'missing'), str(self.archive/'recordings')):
                with self.subTest(path=path):
                    self.assertEqual(client.put(SETTINGS, json={'directory':path}, headers=CLIENT).status_code, 422)
            self.assertEqual(client.put(SETTINGS, json={'directory':str(self.source)}).status_code, 403)
            self.assertEqual(client.put(SETTINGS, json={'directory':str(self.source)}, headers=CLIENT).status_code, 200)
            self.assertIsNone(client.put(SETTINGS, json={'directory':None}, headers=CLIENT).json()['directory'])
        with TestClient(create_app(self.archive)) as client:
            self.assertIsNone(client.get(SETTINGS).json()['directory'])
            self.assertEqual(client.get(SETTINGS).json()['scan']['state'], 'idle')
