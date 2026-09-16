"""Native GPS samples projected into one recording-wide local coordinate frame."""
from bisect import bisect_left
import math
from .alignment import continuous_at

EARTH_RADIUS_M = 6371000.0


def valid_coordinate(latitude, longitude):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in (latitude, longitude)) and abs(latitude) <= 90 and abs(longitude) <= 180


def local_xy(latitude, longitude, origin):
    delta_lon = (longitude-origin[1]+180) % 360-180
    return (EARTH_RADIUS_M*math.radians(delta_lon)*math.cos(math.radians(origin[0])),
            EARTH_RADIUS_M*math.radians(latitude-origin[0]))


def unavailable(reason):
    return {'available':False, 'reason':reason, 'points':[]}


def lap_trajectory(recording, ordinal):
    latitude = recording.position_series.get('latitude')
    longitude = recording.position_series.get('longitude')
    if latitude is None or longitude is None:
        return unavailable('缺少可靠的 GPS 经纬度；驾驶曲线仍可查看。')
    if latitude.frequency_hz != longitude.frequency_hz or latitude.times_s != longitude.times_s:
        return unavailable('经纬度采样时间不一致，无法可靠配对。')
    pairs = list(zip(latitude.values, longitude.values))
    # Never center or normalize laps independently; that would erase line differences.
    origin = next(((a,b) for a,b in pairs if valid_coordinate(a,b)), None)
    if origin is None or abs(math.cos(math.radians(origin[0]))) < 1e-6:
        return unavailable('坐标缺失或投影位置不适用。')
    lap = recording.complete_laps[ordinal-1]
    left = bisect_left(latitude.times_s, lap.start_s)
    right = bisect_left(latitude.times_s, lap.end_s)
    distance = recording.series.get('distance')
    if distance:
        dl = bisect_left(distance.times_s, lap.start_s)
        dr = bisect_left(distance.times_s, lap.end_s)
        dtimes, dvalues = distance.times_s[dl:dr], distance.values[dl:dr]
    points, previous, gaps = [], None, 0
    for index in range(left, right):
        timestamp = latitude.times_s[index]
        a, b = pairs[index]
        dist = continuous_at(dtimes, dvalues, timestamp, 1.5/distance.frequency_hz, True)[0] if distance else None
        point = {'time_s':timestamp-lap.start_s, 'distance_m':dist,
                 'x_m':None, 'y_m':None, 'break_before':True}
        if valid_coordinate(a,b):
            x, y = local_xy(a,b,origin)
            point.update(x_m=x, y_m=y)
            if previous:
                elapsed = timestamp-previous[0]
                jump = math.hypot(x-previous[1],y-previous[2])
                contiguous = 0 < elapsed <= 1.5/latitude.frequency_hz and jump <= max(25.0,elapsed*140.0)
                point['break_before'] = not contiguous
                if not contiguous:
                    gaps += 1
            previous = (timestamp,x,y)
        else:
            if previous:
                gaps += 1
            previous = None
        points.append(point)
    finite = [p for p in points if p['x_m'] is not None]
    if len(finite) < 3:
        return unavailable('本圈有效坐标不足，无法绘制走线。')
    width = max(p['x_m'] for p in finite)-min(p['x_m'] for p in finite)
    height = max(p['y_m'] for p in finite)-min(p['y_m'] for p in finite)
    if max(width,height) < 1:
        return unavailable('本圈坐标没有足够的位移。')
    if max(width,height) > 100000:
        return unavailable('本圈坐标跨度异常，已暂停走线展示。')
    return {'available':True, 'points':points, 'frequency_hz':latitude.frequency_hz,
            'frame':{'projection':'local_equirectangular', 'origin_deg':list(origin)},
            'gap_count':gaps, 'time_basis':'reconstructed_gps_stride',
            'note':'同一练习共用坐标原点；经纬度仅投影为局部轨迹，不叠加真实地图。原始采样相位及坐标精度有限，缺口不连线。'}
