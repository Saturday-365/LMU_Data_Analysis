import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lmu_data_analysis.vehicles import vehicle_brand
from lmu_data_analysis.web_service import catalog_overview


def record(name, laps, *, layout='Monza', kind='Race', entry='Garage 59 2026 #10:LM', duration=500):
    return {'id': name, 'driver_id': 'local', 'created_at': '2026-11-24T00:00Z', 'filename': name + '.duckdb',
            'summary': {'metadata': {'TrackName': 'Monza', 'TrackLayout': layout, 'CarName': entry, 'CarClass': 'GT3',
                                     'SessionType': kind, 'RecordingTime':'2026-11-20T12_30_05Z'},
                        'complete_laps': [{'complete_lap_number': i, 'lap_time_s': t, 'contains_pit_state': pit}
                                          for i, (t, pit) in enumerate(laps, 1)],
                        'recording_start_s': 0, 'recording_end_s': duration}}


class OverviewTests(unittest.TestCase):
    def test_catalog_top_five_averages_only_fastest_eligible_laps(self):
        laps = [(106, False), (90, True), (101, False), (108, False),
                (102, False), (104, False), (100, False), (None, False), (0, False), (103, False)]
        rows = [record('many', laps), record('five', [(time, False) for time in range(100, 105)]),
                record('few', [(100, False)] * 4 + [(90, True)]), record('none', [(90, True)])]
        many, five, few, none = [item['pace'] for item in catalog_overview(rows)['items']]
        self.assertEqual((many['best_s'], many['best_ordinal'], many['top5_mean_s']), (100, 7, 102))
        self.assertEqual(five['top5_mean_s'], 102)
        self.assertEqual((few['best_s'], few['top5_mean_s']), (100, None))
        self.assertIsNone(none['top5_mean_s'])

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

    def test_race_duration_buckets_use_recording_duration_and_keep_separate_medians(self):
        rows = [record(str(index), [(lap, False)], duration=length)
                for index, (length, lap) in enumerate([(1199, 90), (1200, 110), (2399, 132), (2400, 140), (3600, 180)])]
        rows.append(record('practice', [(20, False)], kind='Practice', duration=3600))
        card = catalog_overview(rows)['overview']['layouts'][0]
        by_duration = card['race_durations']
        self.assertEqual({key: rows[0]['pace']['median_s'] for key, rows in by_duration.items()},
                         {'short':90,'medium':121,'long':140,'endurance':180})
        self.assertEqual(card['groups'][0]['pace']['median_s'],132)
        self.assertEqual(card['sessions'],6)
