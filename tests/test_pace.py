import unittest

from test_reader import ROOT
from lmu_data_analysis.models import Recording, Segment
from lmu_data_analysis.pace import analyze_pace, distribution, setup_labels


class PaceTests(unittest.TestCase):
    def recording(self, events):
        segments = [Segment(index, index, 'complete', left, right, right - left,
                            contains_pit_state=in_pits)
                    for index, (left, right, in_pits) in enumerate(
                        [(0, 10, False), (10, 22, False), (22, 30, True), (41, 53, False),
                         (53, 65, False), (65, 77, False), (77, 89, False), (89, 102, True)], 1)]
        return Recording('test.duckdb', 'fixture', {}, [0, 120], [], {}, segments, pit_events=events)

    def test_stints_ignore_repeated_states_and_distinguish_truncated_visits(self):
        data = analyze_pace(self.recording([(0, 0), (15, 0), (29, 1), (40, 0), (90, 1)]), [])
        self.assertEqual(data['statistics']['count'], 6)
        self.assertEqual(data['excluded_count'], 2)
        self.assertEqual([stint['lap_ordinals'] for stint in data['stints']], [[1, 2], [4, 5, 6, 7]])
        self.assertEqual([stint['start_kind'] for stint in data['stints']], ['recording_start', 'pit_exit'])
        self.assertEqual([visit['end_kind'] for visit in data['pit_visits']], ['pit_exit', 'recording_end'])
        self.assertEqual(data['pit_visits'][0]['duration_s'], 11)

    def test_missing_or_partial_pit_observation_does_not_invent_stints(self):
        for events in ([], [(0, 2)], [(0, 0), (121, 1)]):
            with self.subTest(events=events):
                data = analyze_pace(self.recording(events), [])
                self.assertEqual(data['stints'], [])
                self.assertTrue(data['stint_reason'])
                self.assertEqual(data['unassigned_count'], 6)
        partial = analyze_pace(self.recording([(42, 0), (90, 1)]), [])
        self.assertEqual(partial['stints'][0]['start_kind'], 'first_observation')
        self.assertEqual(partial['stints'][0]['lap_ordinals'], [5, 6, 7])
        self.assertEqual(partial['unassigned_count'], 3)

    def test_distribution_and_setup_labels_use_counted_laps(self):
        laps = [{'ordinal': i, 'lap_id': str(i), 'eligible': True, 'time_s': time}
                for i, time in enumerate([10, 11, 12, 13, 14, 15], 1)]
        stats = distribution(laps)
        self.assertEqual((stats['p10_s'], stats['median_s'], stats['p90_s']), (10.5, 12.5, 14.5))
        self.assertEqual(stats['last_vs_first_s'], 3)
        self.assertIsNone(distribution(laps[:4])['p90_s'])
        self.assertIsNone(distribution(laps[:5])['last_vs_first_s'])
        labels = setup_labels(laps + [{'eligible': False, 'lap_id': '7'}], [
            {'scope': 'session', 'field': 'setup_name', 'data': {'state': 'known', 'value': 'A'}},
            {'scope': '1', 'field': 'setup_name', 'data': {'state': 'known', 'value': 'B'}},
            {'scope': '2', 'field': 'setup_name', 'data': {'state': 'unknown', 'value': None}},
        ])
        self.assertEqual(labels, {'names': [{'name': 'B', 'count': 1}, {'name': 'A', 'count': 4}],
                                  'unknown_count': 1})
