"""Projection, shared coordinate frame, missing samples and real GPS verification."""
from pathlib import Path
import sys
import math
import os
import statistics
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from lmu_data_analysis.models import Recording, Segment, Series
from lmu_data_analysis.reader import read_recording, digest
from lmu_data_analysis.trajectory import lap_trajectory, local_xy


def recording():
    times = [i/10 for i in range(200)]
    latitude = [60+math.sin(i%100/100*2*math.pi)*.001 for i in range(200)]
    longitude = [math.cos(i%100/100*2*math.pi)*.002+(0 if i<100 else .00002) for i in range(200)]
    return Recording('gps.duckdb','',{},times,[],{
        'distance':Series('distance','Lap Dist','m','continuous',times,[i%100*7 for i in range(200)],10)},[
        Segment(1,1,'complete',0,10,10),Segment(2,2,'complete',10,20,10)],position_series={
        'latitude':Series('latitude','GPS Latitude','deg','continuous',times,latitude,10),
        'longitude':Series('longitude','GPS Longitude','deg','continuous',times,longitude,10)})


class TrajectoryTests(unittest.TestCase):
    def setUp(self):
        self.r = recording()

    def test_shared_origin_preserves_offset_between_laps(self):
        first, second = lap_trajectory(self.r,1),lap_trajectory(self.r,2)
        self.assertEqual(first['frame'],second['frame'])
        self.assertEqual(len(first['points']),100)
        self.assertEqual(second['points'][0]['time_s'],0)
        offset = second['points'][0]['x_m']-first['points'][0]['x_m']
        self.assertAlmostEqual(offset,6371000*math.radians(.00002)*.5,places=5)
        self.assertEqual(first['points'][-1]['distance_m'],693)
        self.assertTrue(first['points'][0]['break_before'])

    def test_longitude_scaling_and_date_line(self):
        x,y = local_xy(60.001,.002,(60,0))
        self.assertAlmostEqual(x,y,places=6)
        self.assertLess(abs(local_xy(0,-179.999,(0,179.999))[0]),300)

    def test_invalid_pair_keeps_gap_and_breaks_following_segment(self):
        self.r.position_series['latitude'].values[20]=None
        self.r.position_series['longitude'].values[30]=float('inf')
        result=lap_trajectory(self.r,1)
        self.assertIsNone(result['points'][20]['x_m'])
        self.assertIsNone(result['points'][30]['y_m'])
        self.assertTrue(result['points'][21]['break_before'])
        self.assertEqual(result['gap_count'],2)

    def test_jump_does_not_connect_two_positions(self):
        self.r.position_series['longitude'].values[25]+=.05
        result=lap_trajectory(self.r,1)
        self.assertTrue(result['points'][25]['break_before'])
        self.assertTrue(result['points'][26]['break_before'])

    def test_no_cross_lap_coordinate_or_distance_extrapolation(self):
        self.r.segments[0].start_s=.05
        result=lap_trajectory(self.r,1)
        self.assertAlmostEqual(result['points'][0]['time_s'],.05)
        self.assertEqual(len(result['points']),99)
        self.assertEqual(result['points'][0]['distance_m'],7)

    def test_missing_or_unpaired_gps_is_optional(self):
        del self.r.position_series['longitude']
        self.assertFalse(lap_trajectory(self.r,1)['available'])
        self.r=recording()
        self.r.position_series['longitude'].frequency_hz=5
        self.assertFalse(lap_trajectory(self.r,1)['available'])

    def test_missing_distance_retains_time_based_map(self):
        self.r.series={}
        result=lap_trajectory(self.r,1)
        self.assertTrue(result['available'])
        self.assertTrue(all(p['distance_m'] is None for p in result['points']))

    def test_constant_coordinates_are_not_a_track(self):
        self.r.position_series['latitude'].values=[60]*200
        self.r.position_series['longitude'].values=[0]*200
        self.assertFalse(lap_trajectory(self.r,1)['available'])


@unittest.skipUnless(os.environ.get('LMU_SAMPLE_PATH'),'Set LMU_SAMPLE_PATH for real GPS acceptance')
class RealTrajectoryTests(unittest.TestCase):
    def test_monza_native_samples_and_speed_consistency(self):
        path=Path(os.environ['LMU_SAMPLE_PATH'])
        before=digest(path)
        recording=read_recording(path)
        tracks=[lap_trajectory(recording,i) for i in range(1,5)]
        self.assertTrue(all(t['available'] for t in tracks))
        self.assertTrue(all(t['frame']==tracks[0]['frame'] for t in tracks))
        self.assertTrue(all(t['frequency_hz']==10 for t in tracks))
        self.assertTrue(all(1100<len(t['points'])<1160 for t in tracks))
        for track in tracks:
            points=track['points']
            length=sum(math.hypot(b['x_m']-a['x_m'],b['y_m']-a['y_m']) for a,b in zip(points,points[1:]) if not b['break_before'])
            self.assertTrue(5600<length<5900)
        # A sustained speed mismatch would expose a wrong longitude scale.
        lat=recording.position_series['latitude']; lon=recording.position_series['longitude']
        origin=tracks[0]['frame']['origin_deg']
        xy=[local_xy(a,b,origin) for a,b in zip(lat.values,lon.values)]
        speeds=recording.series['speed'].values[::10]
        ratios=[math.dist(a,b)*10/(speeds[i]/3.6) for i,(a,b) in enumerate(zip(xy,xy[1:])) if speeds[i]>80]
        self.assertAlmostEqual(statistics.median(ratios),1,delta=.02)
        self.assertEqual(digest(path),before)
