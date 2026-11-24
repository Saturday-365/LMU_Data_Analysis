"""同布局双圈的距离计时与走线对齐。"""

from bisect import bisect_left, bisect_right
from math import cos, radians

from .trajectory import local_xy


def layout_key(metadata):
    return tuple(str(metadata.get(field) or '').strip().casefold() for field in ('TrackName', 'TrackLayout'))


def share_trajectory_frame(traces):
    current, reference = (trace['trajectory'] for trace in traces)
    if not current['available'] or not reference['available'] or current['frame'] == reference['frame']:
        return
    target = current['frame']['origin_deg']
    source = reference['frame']['origin_deg']
    dx, dy = local_xy(*source, target)
    # 两份录制只有投影原点不同。换算平移与经度比例，保留原有断线。
    if abs(dx) > 30000 or abs(dy) > 30000:
        reference.update(available=False, points=[], reason='录制的 GPS 原点相距异常，无法叠加走线。')
        return
    scale = cos(radians(target[0])) / cos(radians(source[0]))
    for point in reference['points']:
        if point['x_m'] is not None:
            point.update(x_m=dx + point['x_m'] * scale, y_m=dy + point['y_m'])
    reference['frame'] = current['frame']


class DistanceClock:
    def __init__(self, trace):
        self.indices = [i for i, value in enumerate(trace['distance_m']) if value is not None]
        self.distances = [trace['distance_m'][i] for i in self.indices]
        self.times = [trace['time_s'][i] for i in self.indices]

    def at(self, distance):
        right = bisect_left(self.distances, distance)
        if right < len(self.distances) and self.distances[right] == distance:
            return self.times[right] if bisect_right(self.distances, distance) == right + 1 else None
        if not 0 < right < len(self.distances) or self.indices[right] != self.indices[right - 1] + 1:
            return None
        left = right - 1
        weight = (distance - self.distances[left]) / (self.distances[right] - self.distances[left])
        return self.times[left] + weight * (self.times[right] - self.times[left])

    def breaks(self):
        for index in range(1, len(self.indices)):
            if self.indices[index] != self.indices[index - 1] + 1:
                yield (self.distances[index - 1] + self.distances[index]) / 2
            elif self.distances[index - 1] == self.distances[index]:
                yield self.distances[index]


def compare_distance(traces):
    if not all(trace['distance_available'] for trace in traces):
        return {'comparable': False, 'reason': '至少一圈缺少可靠的单调赛道距离。'}
    current, reference = (DistanceClock(trace) for trace in traces)
    start = max(current.distances[0], reference.distances[0])
    end = min(current.distances[-1], reference.distances[-1])
    covers_lap_edges = all(clock.times[0] <= .35 and trace['time_s'][-1] - clock.times[-1] <= .35
                           for clock, trace in zip((current, reference), traces))
    if (max(abs(current.distances[0]), abs(reference.distances[0])) > 25 or end <= start
            or abs(current.distances[-1] - reference.distances[-1]) > 25 or not covers_lap_edges):
        return {'comparable': False, 'reason': '两圈的距离起点或终点覆盖不一致。'}

    # 固定距离网格用于显示，额外保留原始缺口位置，防止图表跨缺口连线。
    count = min(4000, max(2, round((end - start) / 2)))
    gaps = {value for clock in (current, reference) for value in clock.breaks() if start <= value <= end}
    distances = sorted({start, end, *(start + (end - start) * i / count for i in range(1, count)), *gaps})
    values = []
    for distance in distances:
        a, b = current.at(distance), reference.at(distance)
        values.append(None if distance in gaps or a is None or b is None else a - b)
    if sum(value is not None for value in values) < 2:
        return {'comparable': True, 'reason': '共同覆盖区间内的可靠样点不足。'}

    current_time, reference_time = (trace['lap_time_s'] for trace in traces)
    official_delta = None if current_time is None or reference_time is None else current_time - reference_time
    end_delta = values[-1]
    residual = None if end_delta is None or official_delta is None else end_delta - official_delta
    if residual is not None and abs(residual) > 0.15:
        return {'comparable': True, 'reason': '共同覆盖终点的时间差与记录圈时差超过 0.15 秒，已停用累计时间差。'}
    return {'comparable': True, 'distance_m': distances, 'values': values, 'finish_residual_s': residual,
            'reason': '仅比较共同覆盖区间。终点未能用两圈记录圈时核对。' if residual is None
                      else '仅比较共同覆盖区间。终点时间差已与记录圈时差核对。'}
