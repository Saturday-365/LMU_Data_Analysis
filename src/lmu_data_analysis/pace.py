"""使用遥测进出站事件划分连续驾驶段，并计算圈速分布。"""

from collections import Counter
from statistics import median, pstdev, quantiles

from .timing import eligible_lap

TOLERANCE = 1e-6


def distribution(laps):
    times = [lap['time_s'] for lap in laps]
    best = min(laps, key=lambda lap: lap['time_s'], default=None)
    tails = quantiles(times, n=10, method='inclusive') if len(times) >= 5 else None
    return {
        'count': len(times),
        'best_s': best['time_s'] if best else None,
        'best_ordinal': best['ordinal'] if best else None,
        'median_s': median(times) if times else None,
        'slowest_s': max(times) if times else None,
        'stddev_s': pstdev(times) if len(times) >= 2 else None,
        'p10_s': tails[0] if tails else None,
        'p90_s': tails[-1] if tails else None,
        'last_vs_first_s': median(times[-3:]) - median(times[:3]) if len(times) >= 6 else None,
    }


def observed_intervals(events, start, end):
    if not events:
        return None, '文件缺少可用的 In Pits 事件。'
    previous_time = None
    for ts, state in events:
        if (state not in (0, 1) or not start - TOLERANCE <= ts <= end + TOLERANCE
                or (previous_time is not None and ts <= previous_time)):
            return None, 'In Pits 的时间或状态异常，无法可靠分段。'
        previous_time = ts

    # 首条事件是观测状态，只有随后变化才表示进站或出站。
    first, state = events[0]
    left = max(start, min(end, first))
    boundary = 'recording_start' if left - start <= TOLERANCE else 'first_observation'
    intervals = []
    for ts, value in events[1:]:
        if value == state:
            continue
        right = max(start, min(end, ts))
        closing = 'pit_entry' if value == 1 else 'pit_exit'
        if right > left:
            intervals.append((state, left, right, boundary, closing))
        state, left, boundary = value, right, closing
    if end > left:
        intervals.append((state, left, end, boundary, 'recording_end'))
    return intervals, None


def analyze_pace(recording, stored_laps):
    start, end = recording.clock_s[0], recording.clock_s[-1]
    ids = {lap['ordinal']: lap['id'] for lap in stored_laps}
    complete = [
        {'ordinal': ordinal, 'lap_id': ids.get(ordinal), 'time_s': segment.lap_time_s,
         'start_s': segment.start_s - start, 'end_s': segment.end_s - start,
         'eligible': eligible_lap(segment), 'stint': None}
        for ordinal, segment in enumerate(recording.complete_laps, 1)
    ]
    all_eligible = [lap for lap in complete if lap['eligible']]
    intervals, reason = observed_intervals(recording.pit_events, start, end)
    stints, pit_visits = [], []
    for state, left, right, opening, closing in intervals or []:
        relative = {'start_s': left - start, 'end_s': right - start, 'duration_s': right - left,
                    'start_kind': opening, 'end_kind': closing}
        if state == 1:
            if opening == 'pit_entry':
                pit_visits.append(relative)
            continue
        # 仅计入完整落在赛道段内的圈，跨进出站边界的圈保留在整场列表。
        laps = [lap for lap in all_eligible
                if lap['start_s'] >= relative['start_s'] - TOLERANCE
                and lap['end_s'] <= relative['end_s'] + TOLERANCE]
        index = len(stints) + 1
        for lap in laps:
            lap['stint'] = index
        stints.append({'number': index, **relative, 'lap_ordinals': [lap['ordinal'] for lap in laps],
                       'statistics': distribution(laps)})
    return {'duration_s': end - start, 'laps': complete, 'statistics': distribution(all_eligible),
            'excluded_count': len(complete) - len(all_eligible), 'stints': stints, 'pit_visits': pit_visits,
            'stint_reason': reason, 'unassigned_count': sum(lap['stint'] is None for lap in all_eligible)}


def setup_labels(laps, annotations):
    rows = {entry['scope']: entry['data'] for entry in annotations if entry['field'] == 'setup_name'}
    names = Counter()
    unknown = 0
    for lap in laps:
        if not lap['eligible']:
            continue
        entry = rows.get(lap['lap_id'], rows.get('session', {}))
        name = entry['value'].strip() if entry.get('state') == 'known' else None
        if name:
            names[name] += 1
        else:
            unknown += 1
    return {'names': [{'name': name, 'count': count} for name, count in names.items()], 'unknown_count': unknown}
