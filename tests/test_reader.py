"""Synthetic boundary cases plus an opt-in real-recording acceptance check."""

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lmu_data_analysis import TelemetryError, extract_lap, read_recording
from lmu_data_analysis.alignment import continuous_at
from lmu_data_analysis.cli import main
from lmu_data_analysis.models import format_lap_time
from lmu_data_analysis.reader import digest


def fixture(path):
    """30 s synthetic recording: out-lap, two 10 s laps, trailing fragment."""
    with duckdb.connect(str(path)) as c:
        c.execute("CREATE TABLE metadata(key VARCHAR,value VARCHAR)")
        c.executemany("INSERT INTO metadata VALUES (?,?)", [
            ("Version", "1"), ("TrackLayout", "Synthetic test track"),
            ("DriverName", "PRIVATE_TEST_DRIVER"), ("SteamID", "PRIVATE_TEST_ID")])
        c.execute("CREATE TABLE channelsList(channelName VARCHAR,frequency INTEGER,unit VARCHAR)")
        entries = [("GPS Time",100,"s"),("Ground Speed",100,"km/h"),
                   ("Throttle Pos",50,"%"),("Brake Pos",50,"%"),
                   ("Steering Pos",100,"%"),("Lap Dist",10,"m")]
        c.executemany("INSERT INTO channelsList VALUES (?,?,?)", entries)
        for name, rate, unit in entries:
            c.execute(f'CREATE TABLE "{name}"(value DOUBLE)')
            expression = {
                "GPS Time": "i/100.0", "Ground Speed": "100+i/100.0",
                "Throttle Pos": "i%101", "Brake Pos": "i%51",
                "Steering Pos": "(i%201)-100", "Lap Dist": "((i/10.0+5)%10)*100",
            }[name]
            c.execute(f'INSERT INTO "{name}" SELECT {expression} FROM range({rate*30}) t(i)')
        c.execute("CREATE TABLE eventsList(eventName VARCHAR,unit VARCHAR)")
        for name, unit, rows in [
            ("Lap","",[(0,0),(5,1),(15,2),(25,3)]),
            ("Lap Time","s",[(0,0),(15,10),(25,10)]),
            ("In Pits","",[(0,1),(2,0)]),
            ("Gear","",[(0,0),(4,3),(7.345,4),(14.9,2),(20.015,5)]),
        ]:
            c.execute("INSERT INTO eventsList VALUES (?,?)",[name,unit])
            c.execute(f'CREATE TABLE "{name}"(ts DOUBLE,value DOUBLE)')
            c.executemany(f'INSERT INTO "{name}" VALUES (?,?)',rows)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.output_root = (ROOT / "outputs").resolve()
        self.output_root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="reader-test-", dir=self.output_root)
        self.folder = Path(self.temporary.name).resolve()
        self.addCleanup(self.clean_up)
        self.source = self.folder / "synthetic.duckdb"
        fixture(self.source)

    def clean_up(self):
        # Validate the absolute cleanup target before recursive Windows cleanup.
        if self.folder.parent != self.output_root or not self.folder.name.startswith("reader-test-"):
            raise RuntimeError("Unexpected test cleanup target")
        self.temporary.cleanup()

    def change(self, sql):
        with duckdb.connect(str(self.source)) as c:
            c.execute(sql)

    def test_readonly_segments_units_and_metadata(self):
        before = digest(self.source)
        recording = read_recording(self.source)
        self.assertEqual(before, digest(self.source))
        self.assertEqual([s.kind for s in recording.segments],
                         ["out_lap","complete","complete","trailing_fragment"])
        self.assertEqual([s.lap_time_s for s in recording.complete_laps],[10,10])
        self.assertTrue(all(s.validity == "unknown" for s in recording.segments))
        self.assertTrue(all(x['matched'] for x in recording.distance_boundary_checks))
        self.assertEqual(recording.series['speed'].values[0],100)
        self.assertEqual(recording.series['steering'].unit,'%')
        self.assertNotIn('DriverName',recording.metadata)
        self.assertNotIn('SteamID',recording.metadata)

    def test_alignment_linear_hold_edges_and_no_cross_lap_interpolation(self):
        lap = extract_lap(read_recording(self.source),1)
        aligned = lap['aligned']
        values = aligned['channels']
        self.assertEqual(aligned['session_time_s'][0],5)
        self.assertAlmostEqual(values['speed']['values'][1],105.01)
        self.assertEqual(values['throttle']['provenance'][1],'interpolated')
        self.assertAlmostEqual(values['throttle']['values'][1],48.5)
        self.assertEqual(values['gear']['values'][0],3)
        self.assertEqual(values['gear']['provenance'][0],'held')
        before = aligned['session_time_s'].index(7.34)
        after = aligned['session_time_s'].index(7.35)
        self.assertEqual(values['gear']['values'][before],3)
        self.assertEqual(values['gear']['values'][after],4)
        self.assertIsNone(values['distance']['values'][-1])
        self.assertEqual(values['distance']['provenance'][-1],'missing')
        self.assertLess(lap['native']['speed']['session_time_s'][-1],15)
        self.assertEqual(lap['native']['gear']['state_at_start']['value'],3)

    def test_missing_channel_keeps_other_data(self):
        self.change('DROP TABLE "Throttle Pos"')
        recording = read_recording(self.source)
        self.assertNotIn('throttle',recording.series)
        self.assertIn('speed',recording.series)
        self.assertTrue(any(d.code=='channel_missing' for d in recording.diagnostics))

    def test_unknown_unit_is_not_silently_converted(self):
        self.change("UPDATE channelsList SET unit='m/s' WHERE channelName='Ground Speed'")
        recording = read_recording(self.source)
        self.assertNotIn('speed',recording.series)
        self.assertTrue(any(d.code=='unit_unsupported' for d in recording.diagnostics))

    def test_sample_count_mismatch_excludes_channel(self):
        self.change('DELETE FROM "Brake Pos" WHERE rowid=1499')
        recording = read_recording(self.source)
        self.assertNotIn('brake',recording.series)
        self.assertTrue(any(d.code=='sample_count_mismatch' for d in recording.diagnostics))

    def test_deleted_middle_row_cannot_shift_timing(self):
        self.change('DELETE FROM "Ground Speed" WHERE rowid=700')
        with self.assertRaisesRegex(TelemetryError,'non-contiguous'):
            read_recording(self.source)

    def test_unsupported_frequency_is_excluded(self):
        self.change("UPDATE channelsList SET frequency=7 WHERE channelName='Brake Pos'")
        recording = read_recording(self.source)
        self.assertNotIn('brake',recording.series)
        self.assertTrue(any(d.code=='frequency_unsupported' for d in recording.diagnostics))

    def test_null_input_is_preserved_and_not_interpolated_through(self):
        self.change('UPDATE "Throttle Pos" SET value=NULL WHERE rowid=251')
        lap = extract_lap(read_recording(self.source),1)
        values=lap['aligned']['channels']['throttle']['values']
        self.assertIsNone(values[1])
        self.assertIsNone(values[2])
        self.assertIsNone(values[3])

    def test_clock_pause_is_explicitly_rejected(self):
        self.change('UPDATE "GPS Time" SET value=value+1 WHERE rowid>=1000')
        with self.assertRaisesRegex(TelemetryError,'non-uniform'):
            read_recording(self.source)

    def test_event_duplicate_timestamps_rejected(self):
        self.change('INSERT INTO "Gear" VALUES (4,5)')
        with self.assertRaisesRegex(TelemetryError,'timestamps'):
            read_recording(self.source)

    def test_recording_started_mid_lap_not_claimed_complete(self):
        self.change('UPDATE "Lap" SET value=value+8')
        self.change('UPDATE "In Pits" SET value=0')
        recording=read_recording(self.source)
        self.assertEqual(recording.segments[0].kind,'leading_fragment')
        self.assertEqual(len(recording.complete_laps),2)

    def test_counter_reset_does_not_create_fake_lap(self):
        self.change('UPDATE "Lap" SET value=0 WHERE ts=15')
        recording=read_recording(self.source)
        self.assertEqual(len(recording.complete_laps),0)
        self.assertTrue(any(d.code=='lap_counter_discontinuity' for d in recording.diagnostics))

    def test_lap_time_disagreement_is_not_normal_lap(self):
        self.change('UPDATE "Lap Time" SET value=12 WHERE ts=15')
        recording=read_recording(self.source)
        self.assertEqual(recording.segments[1].kind,'timing_mismatch')
        self.assertEqual(len(recording.complete_laps),1)

    def test_missing_lap_time_does_not_invent_official_time(self):
        self.change('DROP TABLE "Lap Time"')
        recording=read_recording(self.source)
        self.assertEqual(len(recording.complete_laps),2)
        self.assertTrue(all(s.lap_time_s is None for s in recording.complete_laps))

    def test_distance_mismatch_disables_distance_not_time(self):
        self.change('UPDATE "Lap Dist" SET value=rowid')
        recording=read_recording(self.source)
        self.assertNotIn('distance',recording.series)
        self.assertIn('speed',recording.series)
        self.assertEqual(len(recording.complete_laps),2)

    def test_missing_corrupt_unknown_version_and_empty_clock(self):
        with self.assertRaises(TelemetryError):
            read_recording(self.folder/'missing.duckdb')
        corrupt=self.folder/'corrupt.duckdb'
        corrupt.write_bytes(b'not a database')
        with self.assertRaises(TelemetryError):
            read_recording(corrupt)
        self.change("UPDATE metadata SET value='2' WHERE key='Version'")
        with self.assertRaisesRegex(TelemetryError,'Version'):
            read_recording(self.source)
        self.change("UPDATE metadata SET value='1' WHERE key='Version'")
        self.change('DELETE FROM "GPS Time"')
        with self.assertRaisesRegex(TelemetryError,'two finite'):
            read_recording(self.source)

    def test_cli_export_and_overwrite_guard(self):
        output=self.folder/'lap.json'
        with redirect_stdout(StringIO()):
            self.assertEqual(main([str(self.source),'--lap','2','--output',str(output)]),0)
            before=output.read_bytes()
            self.assertEqual(main([str(self.source),'--output',str(output)]),1)
            self.assertEqual(before,output.read_bytes())
            self.assertEqual(main([str(self.source),'--lap','99','--output',str(self.folder/'bad.json')]),1)
            self.assertFalse((self.folder/'bad.json').exists())
            self.assertEqual(main([str(self.source),'--output',str(self.source)]),1)
        content=json.loads(before)
        self.assertEqual(content['selected_lap']['complete_lap_number'],2)
        self.assertNotIn('PRIVATE_TEST_DRIVER',before.decode())

    def test_no_interpolation_across_large_gap_or_reverse_distance(self):
        self.assertEqual(continuous_at([0,1],[0,10],0.5,0.02),(None,'missing'))
        self.assertEqual(continuous_at([0,.1],[100,0],.05,.15,True),(None,'missing'))


@unittest.skipUnless(os.environ.get('LMU_SAMPLE_PATH'),'Set LMU_SAMPLE_PATH for real sample acceptance')
class RealRecordingTests(unittest.TestCase):
    def test_confirmed_monza_sample(self):
        source=Path(os.environ['LMU_SAMPLE_PATH'])
        before=digest(source)
        recording=read_recording(source)
        self.assertEqual(digest(source),before)
        self.assertEqual([format_lap_time(s.lap_time_s) for s in recording.complete_laps],
                         ['1:54.641','1:54.307','1:54.273','1:53.339'])
        self.assertEqual(len(recording.catalog),98)
        self.assertEqual(set(recording.series),{'speed','throttle','brake','steering','distance','gear'})
        self.assertEqual(len(recording.distance_boundary_checks),5)
        self.assertTrue(all(item['matched'] for item in recording.distance_boundary_checks))
        for number in range(1,5):
            lap=extract_lap(recording,number)
            size=len(lap['aligned']['session_time_s'])
            self.assertGreater(size,11000)
            for key, values in lap['aligned']['channels'].items():
                self.assertEqual(len(values['values']),size,key)
                self.assertEqual(len(values['provenance']),size,key)
            self.assertTrue(all(value is None or int(value)==value
                                for value in lap['aligned']['channels']['gear']['values']))


if __name__ == '__main__':
    unittest.main()
