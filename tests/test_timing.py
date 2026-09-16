"""Sector semantics, missing data, statistic scope and a real-file acceptance check."""
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lmu_data_analysis.models import Recording, Segment
from lmu_data_analysis.reader import read_recording, digest
from lmu_data_analysis.timing import timing_summary
from lmu_data_analysis.inventory import inspect_channels


def recording():
    return Recording('synthetic.duckdb', '', {}, [0, 20], [], {}, [
        Segment(1,1,'complete',0,10,10), Segment(2,2,'complete',10,20,10)], timing_events={
        'Current Sector':[(0,1),(3,2),(7,0),(10,1),(14,2),(17,0),(20,1)],
        'Current Sector1':[(3,3),(14,4)], 'Current Sector2':[(7,7),(17,7)],
        'Last Sector1':[(10,3),(20,4)], 'Last Sector2':[(10,7),(20,7)]})


class TimingTests(unittest.TestCase):
    def setUp(self):
        self.recording = recording()

    def report(self):
        return timing_summary(self.recording, [{'ordinal':1,'id':'lap-a'},{'ordinal':2,'id':'lap-b'}])

    def test_cumulative_second_sector_and_theoretical_sources(self):
        data = self.report()
        self.assertEqual(data['rows'][0]['sectors_s'], [3,4,3])
        self.assertEqual(data['rows'][1]['sectors_s'], [4,3,3])
        self.assertEqual(data['rows'][0]['lap_id'], 'lap-a')
        self.assertEqual(data['statistics']['theoretical_s'], 9)
        self.assertEqual(data['statistics']['best_sector_laps'], [[1],[2],[1,2]])
        self.assertEqual(data['statistics']['average_s'], 10)
        self.assertEqual(data['statistics']['stddev_s'], 0)
        self.assertEqual(data['statistics']['gap_to_theoretical_s'], 1)

    def test_missing_events_do_not_reuse_previous_lap(self):
        self.recording.timing_events['Last Sector1'] = [(10,3)]
        self.recording.timing_events['Current Sector1'] = [(3,3)]
        self.assertEqual(self.report()['rows'][1]['sectors_s'], [None,None,3])

    def test_current_field_fallback_without_last_snapshot(self):
        self.recording.timing_events.pop('Last Sector1')
        self.recording.timing_events.pop('Last Sector2')
        self.assertEqual(self.report()['rows'][1]['sectors_s'], [4,3,3])

    def test_missing_whole_sector_makes_theoretical_unknown(self):
        self.recording.timing_events.pop('Last Sector2')
        self.recording.timing_events.pop('Current Sector2')
        data = self.report()
        self.assertIsNone(data['statistics']['theoretical_s'])
        self.assertEqual(data['statistics']['average_s'], 10)
        self.assertEqual(data['rows'][0]['sectors_s'], [3,None,None])

    def test_mismatched_snapshot_rejected(self):
        self.recording.timing_events['Last Sector2'][0] = (10,6)
        self.assertEqual(self.report()['rows'][0]['sectors_s'], [3,None,None])

    def test_cumulative_value_must_match_transition(self):
        self.recording.timing_events['Last Sector2'][0] = (10,4)
        self.recording.timing_events['Current Sector2'][0] = (7,4)
        self.assertEqual(self.report()['rows'][0]['sectors_s'], [3,None,None])

    def test_wrong_transition_sequence_rejects_splits(self):
        self.recording.timing_events['Current Sector'][2] = (7,2)
        self.assertEqual(self.report()['rows'][0]['sectors_s'], [None]*3)

    def test_pit_lap_and_fragment_excluded_from_all_statistics(self):
        self.recording.segments[0].contains_pit_state = True
        self.recording.segments.append(Segment(3,3,'trailing_fragment',20,29,None))
        self.recording.timing_events['Current Sector'] += [(21,2),(22,0)]
        self.recording.timing_events['Current Sector1'] += [(21,1)]
        self.recording.timing_events['Current Sector2'] += [(22,2)]
        data = self.report()
        self.assertEqual(data['rows'][2]['sectors_s'], [1,1,None])
        self.assertEqual(data['statistics']['count'], 1)
        self.assertEqual(data['statistics']['theoretical_s'], 10)
        self.assertEqual(data['statistics']['best_sectors_s'], [4,3,3])

    def test_no_eligible_laps_have_null_statistics_not_zero(self):
        for segment in self.recording.segments:
            segment.lap_time_s = None
        s = self.report()['statistics']
        self.assertEqual(s['count'], 0)
        self.assertIsNone(s['average_s'])
        self.assertIsNone(s['theoretical_s'])
        self.assertIsNone(s['stddev_s'])


@unittest.skipUnless(os.environ.get('LMU_SAMPLE_PATH'), 'Set LMU_SAMPLE_PATH for real timing acceptance')
class RealTimingTests(unittest.TestCase):
    def test_monza_sectors_statistics_and_channel_inventory(self):
        path = Path(os.environ['LMU_SAMPLE_PATH'])
        before = digest(path)
        r = read_recording(path)
        data = timing_summary(r, [])
        s = data['statistics']
        self.assertEqual(s['count'], 4)
        self.assertAlmostEqual(s['average_s'], 114.13995361328125)
        self.assertAlmostEqual(s['theoretical_s'], 112.934326171875)
        self.assertEqual(s['best_sector_laps'], [[4],[4],[3]])
        for row in data['rows']:
            if row['eligible']:
                self.assertAlmostEqual(sum(row['sectors_s']), row['lap_time_s'])
        inv = inspect_channels(path,r)
        self.assertEqual((inv['continuous_count'],inv['event_count']), (56,42))
        channels = {item['source_name']:item for item in inv['items']}
        self.assertEqual(channels['Engine RPM']['status'], 'candidate')
        self.assertEqual(channels['Fuel Level']['status'], 'constant')
        self.assertEqual(channels['Engine Water Temp']['status'], 'timing_review')
        self.assertEqual(channels['TyresPressure']['status'], 'mapping_review')
        self.assertEqual(channels['Fuel Level']['components'][0]['min'],92)
        self.assertEqual(digest(path),before)
