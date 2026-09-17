"""Practice context, migration and fail-closed geometry acceptance."""
from contextlib import contextmanager, closing
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

import duckdb
from fastapi.testclient import TestClient
from test_reader import ROOT, fixture
from lmu_data_analysis.reader import read_recording, digest
from lmu_data_analysis.storage import SQLiteSessionRepository
from lmu_data_analysis.web_app import create_app
from lmu_data_analysis.track_reference import validate_resource, load_reference
from lmu_data_analysis.conditions import extract_context


class Identity:
    def current_driver(self, request):
        return request.headers.get('x-owner', 'a')


def geometry(recording):
    fit = [[0,0],[100,0],[0,100]]
    checks = [[20,0],[100,20],[100,80],[80,100],[20,100],[0,80],[0,20],[50,100]]
    def landmarks(points, prefix):
        return [dict(id=f'{prefix}{i}', source=p, target=p, lap_fraction=i/len(points)) for i,p in enumerate(points)]
    origin = [recording.position_series['latitude'].values[0], recording.position_series['longitude'].values[0]]
    return dict(schema_version=1, source='Synthetic fixture only', license='Test geometry authored here',
                track='Test', layout='Synthetic test track', version='test-1', coordinate_system='synthetic xy', unit='m',
                recording_sha256=recording.source_sha256,
                frame={'projection':'local_equirectangular','origin_deg':origin},
                transform=dict(scale=1,rotation_rad=0,translation_m=[0,0]),
                validation=dict(threshold_m=1,threshold_basis='Synthetic known geometry, not Monza', reviewer='test',
                                threshold_set_at='2026-09-01T00:00:00+00:00', checked_at='2026-09-02T00:00:00+00:00',
                                fit_points=landmarks(fit,'fit'),check_points=landmarks(checks,'check')),
                layers=[dict(kind='left_boundary', paths=[[[0,0],[100,0]],[[100,20],[100,100]]])])


class V02Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='v02-test-', dir=ROOT/'outputs')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder/'sample.duckdb'
        fixture(self.source)
        with duckdb.connect(str(self.source)) as c:
            c.execute("INSERT INTO metadata VALUES ('TrackName','Test')")
            c.execute("INSERT INTO metadata VALUES ('WeatherConditions','Cloudy')")
            for name,rate,unit,expression in [('Fuel Level',20,'L','0'),
                    ('Ambient Temperature',1,'C','i'), ('Track Temperature',1,'C','20+i'),
                    ('GPS Latitude',10,'deg','60+sin(i/100.0)*0.001'),('GPS Longitude',10,'deg','cos(i/100.0)*0.002')]:
                c.execute('INSERT INTO channelsList VALUES (?,?,?)',[name,rate,unit])
                c.execute(f'CREATE TABLE "{name}" AS SELECT {expression} AS value FROM range({30*rate}) t(i)')
        self.before = digest(self.source)
        self.data = self.folder/'data'
        self.client = TestClient(create_app(self.data, identity=Identity()))
        self.addCleanup(self.client.close)
        self.session = self.client.post('/api/v1/sessions', content=self.source.read_bytes(),
            headers={'x-lmu-client':'web','x-filename':'sample.duckdb'}).json()['session']
        self.base = '/api/v1/sessions/'+self.session['id']
        self.lap = self.session['laps'][0]['id']

    def get(self, lap=None, client=None):
        return (client or self.client).get(self.base+'/conditions'+('?lap_id='+lap if lap else '')).json()

    def field(self, data, key):
        return next(f for f in data['fields'] if f['key']==key)

    def edit(self, changes, lap=None, **headers):
        return self.client.patch(self.base+'/conditions'+('?lap_id='+lap if lap else ''), json={'changes':changes},
                                 headers={'x-lmu-client':'web',**headers})

    def test_auto_values_zero_and_lap_range(self):
        full,lap = self.get(), self.get(self.lap)
        self.assertEqual(self.field(full,'fuel')['effective']['value']['min'],0)
        self.assertEqual(self.field(full,'ambient')['effective']['value'],dict(min=0,max=29,first=0,last=29))
        self.assertEqual(self.field(lap,'ambient')['effective']['value'],dict(min=5,max=14,first=5,last=14))
        self.assertEqual(self.field(full,'wind_speed')['effective']['state'],'not_recorded')
        self.assertEqual(self.field(full,'weather')['effective']['value'],'Cloudy')
        self.assertEqual(self.field(lap,'weather')['effective']['state'],'unknown')
        self.assertEqual(self.before,digest(self.source))

    def test_save_inheritance_restore_restart_dedup(self):
        self.assertEqual(self.edit({'fuel':{'state':'known','value':50}}).status_code,200)
        self.assertTrue(self.field(self.get(self.lap),'fuel')['inherited_override'])
        self.edit({'fuel':{'state':'known','value':0}},self.lap)
        f=self.field(self.get(self.lap),'fuel')
        self.assertEqual(f['effective']['value'],0)
        self.assertEqual(f['automatic']['value']['max'],0)
        self.assertEqual(f['effective']['valid_range'],{'scope':self.lap})
        with TestClient(create_app(self.data,identity=Identity())) as client:
            self.assertEqual(self.field(self.get(self.lap,client),'fuel')['effective']['value'],0)
            duplicate=client.post('/api/v1/sessions',content=self.source.read_bytes(),headers={'x-lmu-client':'web','x-filename':'same.duckdb'}).json()
            self.assertTrue(duplicate['duplicate'])
            self.assertEqual(duplicate['session']['laps'],self.session['laps'])
        self.edit({'fuel':None},self.lap)
        self.assertEqual(self.field(self.get(self.lap),'fuel')['effective']['value'],50)
        self.edit({'fuel':None})
        self.assertEqual(self.field(self.get(self.lap),'fuel')['effective']['source'],'telemetry')

    def test_validation_states_and_ownership(self):
        for state in ('unknown','not_recorded','not_applicable'):
            self.assertEqual(self.edit({'fuel':{'state':state,'value':None}}).status_code,200)
            self.assertEqual(self.field(self.get(),'fuel')['effective']['state'],state)
        for value in (-1,1001,True,'12'):
            self.assertEqual(self.edit({'fuel':{'state':'known','value':value}}).status_code,422)
        self.assertEqual(self.edit({'car':{'state':'known','value':'test'}},self.lap).status_code,422)
        self.assertEqual(self.edit({'fuel':{'state':[],'value':None}}).status_code,422)
        self.assertEqual(self.edit({'fuel':{'state':'unknown','value':0}}).status_code,422)
        self.assertEqual(self.edit({'notes':{'state':'known','value':'must not persist'},
                                    'fuel':{'state':'known','value':-1}}).status_code,422)
        self.assertEqual(self.field(self.get(),'notes')['effective']['state'],'not_recorded')
        self.assertEqual(self.edit({'notes':{'state':'known','value':'private'}},**{'x-owner':'b'}).status_code,404)
        for suffix in ('conditions','conditions?lap_id='+self.lap,'track-reference'):
            self.assertEqual(self.client.get(self.base+'/'+suffix,headers={'x-owner':'b'}).status_code,404)
        self.assertEqual(self.edit({'fuel':None},'wrong-lap').status_code,404)
        self.assertEqual(self.client.get(self.base+'/conditions?lap_id=wrong').status_code,404)

    def test_wrong_unit_and_sampling_fail_closed(self):
        with duckdb.connect(str(self.source)) as c:
            c.execute("UPDATE channelsList SET unit='F' WHERE channelName='Ambient Temperature'")
            c.execute('DELETE FROM "Fuel Level" WHERE rowid=5')
        session=self.client.post('/api/v1/sessions',content=self.source.read_bytes(),headers={'x-lmu-client':'web','x-filename':'changed.duckdb'}).json()['session']
        data=self.client.get('/api/v1/sessions/'+session['id']+'/conditions').json()
        for key in ('ambient','fuel'):
            self.assertEqual(self.field(data,key)['effective']['state'],'unknown')
        self.assertEqual(self.field(data,'ambient')['automatic']['raw_unit'],'F')

    def test_migration_preserves_ids_and_backup(self):
        database=self.data/'catalog.sqlite3'
        with closing(sqlite3.connect(database)) as c, c:
            c.execute('DROP TABLE annotations');c.execute('DROP TABLE track_references');c.execute('PRAGMA user_version=1')
        SQLiteSessionRepository(database)
        backups=list(self.data.glob('catalog.sqlite3.pre-v2-*.bak'))
        self.assertEqual(len(backups),1)
        with closing(sqlite3.connect(backups[0])) as c, c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT id FROM sessions').fetchone()[0],self.session['id'])
        migrated=SQLiteSessionRepository(database).get_session('a',self.session['id'])['laps']
        self.assertEqual([lap['id'] for lap in migrated],[lap['id'] for lap in self.session['laps']])

    def test_migration_failure_rolls_back(self):
        database=self.data/'catalog.sqlite3'
        with closing(sqlite3.connect(database)) as c, c:
            c.execute('DROP TABLE annotations');c.execute('DROP TABLE track_references');c.execute('PRAGMA user_version=1')
        class FailingRepository(SQLiteSessionRepository):
            @contextmanager
            def connection(self):
                with super().connection() as c:
                    c.set_authorizer(lambda action,a,b,db,source: sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_TABLE and a=='track_references' else sqlite3.SQLITE_OK)
                    yield c
        with self.assertRaises(sqlite3.DatabaseError):
            FailingRepository(database)
        with closing(sqlite3.connect(database)) as c, c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='annotations'").fetchone())

    def test_reference_validation_and_api(self):
        self.assertFalse(self.client.get(self.base+'/track-reference').json()['available'])
        recording=read_recording(self.source);resource=geometry(recording)
        self.assertTrue(validate_resource(resource,recording)['available'])
        folder=self.data/'track-resources';folder.mkdir()
        (folder/'test.json').write_text(json.dumps(resource),encoding='utf-8')
        with closing(sqlite3.connect(self.data/'catalog.sqlite3')) as c, c:
            c.execute('INSERT INTO track_references VALUES (?,?)',(self.session['id'],'test'))
        result=self.client.get(self.base+'/track-reference').json()
        self.assertTrue(result['available']);self.assertEqual(len(result['layers'][0]['paths']),2)
        variants=[]
        wrong=deepcopy(resource);wrong['layout']='wrong';variants.append(wrong)
        wrong=deepcopy(resource);wrong['recording_sha256']='wrong';variants.append(wrong)
        wrong=deepcopy(resource);wrong['frame']['origin_deg']=[0,0];variants.append(wrong)
        wrong=deepcopy(resource);wrong['validation']['check_points'][0]['target']=[99,99];variants.append(wrong)
        wrong=deepcopy(resource);wrong['validation']['check_points'][0]['id']='fit0';variants.append(wrong)
        wrong=deepcopy(resource);wrong['validation']['threshold_m']=float('nan');variants.append(wrong)
        wrong=deepcopy(resource);wrong['validation']['threshold_set_at']='2027-01-01T00:00:00+00:00';variants.append(wrong)
        wrong=deepcopy(resource);wrong['license']='';variants.append(wrong)
        wrong=deepcopy(resource)
        for p in wrong['validation']['check_points']:p['lap_fraction']=0.1
        variants.append(wrong)
        wrong=deepcopy(resource);wrong['validation']['check_points'][1]['source']=wrong['validation']['check_points'][0]['source'];variants.append(wrong)
        wrong=deepcopy(resource);wrong['layers'][0]['paths'][0][0]=[float('inf'),0];variants.append(wrong)
        for wrong in variants:
            (folder/'test.json').write_text(json.dumps(wrong),encoding='utf-8')
            self.assertFalse(self.client.get(self.base+'/track-reference').json()['available'])
        self.assertFalse(load_reference(folder,'../private',recording)['available'])


@unittest.skipUnless(os.environ.get('LMU_SAMPLE_PATH'), 'Set LMU_SAMPLE_PATH for real context acceptance')
class RealContextTests(unittest.TestCase):
    def test_real_context_and_source_hash(self):
        path=Path(os.environ['LMU_SAMPLE_PATH'])
        before=digest(path)
        recording=read_recording(path)
        channels,metadata=extract_context(path,recording)
        for key in ('ambient','track_temp','wind_speed','wind_heading','fuel'):
            self.assertEqual(channels[key]['state'],'known')
            self.assertTrue(channels[key]['samples'])
        self.assertEqual({v for _,v in channels['fuel']['samples']},{92})
        self.assertTrue(metadata['setup_present'])
        self.assertEqual(before,digest(path))


if __name__=='__main__':
    unittest.main()
