import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lmu_data_analysis.vehicles import vehicle_brand
from lmu_data_analysis.web_service import catalog_overview


def record(name, laps, *, layout='Monza', kind='Race', entry='Garage 59 2026 #10:LM'):
    return {'id': name, 'driver_id': 'local', 'created_at': '2026-11-24T00:00Z', 'filename': name + '.duckdb',
            'summary': {'metadata': {'TrackName': 'Monza', 'TrackLayout': layout, 'CarName': entry, 'CarClass': 'GT3',
                                     'SessionType': kind, 'RecordingTime':'2026-11-20T12_30_05Z'},
                        'complete_laps': [{'complete_lap_number': i, 'lap_time_s': t, 'contains_pit_state': pit}
                                          for i, (t, pit) in enumerate(laps, 1)],
                        'recording_start_s': 0, 'recording_end_s': 500}}


class OverviewTests(unittest.TestCase):
    def test_brand_mapping_is_specific_and_annotations_take_precedence(self):
        metadata = {'CarClass':'GT3','CarName':'Proton Competition 2026 #75:ELMS'}
        self.assertEqual(vehicle_brand(metadata), ('Porsche','entry'))
        metadata['CarName'] = 'Proton Competition 2026 #77:LM'
        self.assertEqual(vehicle_brand(metadata), ('Ford','entry'))
        metadata['CarName'] = 'Logitech G Challenge #2:LGC'
        self.assertEqual(vehicle_brand(metadata), (None,None))
        self.assertEqual(vehicle_brand(metadata, '宝马M4 GT3'), ('BMW','model'))
        self.assertEqual(vehicle_brand(metadata, 'Ford', {'state':'known','value':'迈凯伦'}), ('McLaren','user'))

    def test_counts_all_records_and_pools_original_laps_per_layout_brand_type(self):
        rows = [
            record('first', [(90, False), (120, True)]),
            record('second', [(110, False), (111, False), (113, False), (114, False)],
                   entry='United Autosports 2025 #59:LM'),
            record('qual', [(100, False)], kind='Qualify'),
            record('short', [(45, False)], layout='Short'),
        ]
        data = catalog_overview(rows)['overview']
        self.assertEqual(data['totals'], {'sessions':4, 'layouts':2, 'complete_laps':8, 'pace_laps':7})
        main = next(card for card in data['layouts'] if card['metadata']['TrackLayout'] == 'Monza')
        race, qual = main['groups']
        self.assertEqual((race['brand'], race['sessions'], race['complete_laps'], race['pace_laps']), ('McLaren',2,6,5))
        self.assertEqual(race['pace']['median_s'], 111)
        self.assertEqual((race['best_session'], race['best_ordinal']), ('first',1))
        self.assertIsNotNone(race['pace']['p10_s'])
        self.assertEqual(qual['pace']['median_s'],100)
