"""Recorded split times verified against transitions; never reuse stale sector values."""
import math
from statistics import mean, median, pstdev

TOLERANCE_S = 0.05  # Observed event sampling precision, not display rounding.
KINDS = {"complete": "完整圈", "out_lap": "出站圈", "leading_fragment": "起始残圈",
         "trailing_fragment": "末尾残圈", "discontinuity": "计数不连续", "timing_mismatch": "计时不一致"}


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def at_event(rows, timestamp):
    return next((value for ts, value in rows if abs(ts-timestamp) <= 1e-6), None)


def split_times(recording, segment):
    events = recording.timing_events
    changes = [(ts, value) for ts, value in events.get('Current Sector', [])
               if segment.start_s+1e-6 < ts < segment.end_s-1e-6]
    notes, source = [], [None, None, None]
    # The observed LMU sequence is 1 -> 2 -> 0 (source 0 denotes sector 3).
    states = [value for _, value in changes]
    if states not in ([2], [2, 0]):
        return [None]*3, source, ['没有可核对的 S1 → S2 → S3 分段边界']
    at_start = [value for ts, value in events.get('Current Sector', []) if ts <= segment.start_s+1e-6]
    if not at_start or at_start[-1] != 1:
        return [None]*3, source, ['起始分段状态不明确']

    def cumulative(index):
        if len(changes) < index:
            return None
        boundary = changes[index-1][0]
        current = at_event(events.get(f'Current Sector{index}', []), boundary)
        last = at_event(events.get(f'Last Sector{index}', []), segment.end_s) if segment.kind == 'complete' else None
        candidates = [value for value in (last, current) if positive(value)]
        if not candidates:
            notes.append(f'S{index} 累计计时缺失，不沿用上一圈数值')
            return None
        if max(candidates)-min(candidates) > TOLERANCE_S:
            notes.append(f'S{index} 当前 / 上圈计时字段不一致')
            return None
        value = candidates[0]
        # Fragments lack an observed lap start, so cannot establish elapsed time.
        if segment.kind not in ('complete', 'trailing_fragment'):
            return None
        if abs(value-(boundary-segment.start_s)) > TOLERANCE_S:
            notes.append(f'S{index} 累计计时与本圈分段边界不匹配')
            return None
        source[index-1] = 'Last Sector'+str(index) if positive(last) else 'Current Sector'+str(index)
        return value

    first, cumulative_second = cumulative(1), cumulative(2)
    second = cumulative_second-first if first is not None and cumulative_second is not None else None
    third = segment.lap_time_s-cumulative_second if segment.kind == 'complete' and positive(segment.lap_time_s) and cumulative_second is not None else None
    if (second is not None and second <= 0) or (third is not None and third <= 0):
        return [None]*3, [None]*3, ['分段时间非正，已排除']
    if second is not None:
        source[1] = '累计 S2 − S1'
    if third is not None:
        source[2] = 'Lap Time − 累计 S2'
    return [first, second, third], source, notes


def timing_summary(recording, stored_laps):
    by_ordinal = {lap['ordinal']: lap for lap in stored_laps}
    rows, ordinal = [], 0
    for segment in recording.segments:
        complete = segment.kind == 'complete'
        if complete:
            ordinal += 1
        stored = by_ordinal.get(ordinal) if complete else None
        sectors, sources, notes = split_times(recording, segment)
        eligible = complete and positive(segment.lap_time_s) and not segment.contains_pit_state
        reason = None if eligible else ('不完整或计时异常' if not complete else '包含维修区状态' if segment.contains_pit_state else '缺少已记录圈时')
        rows.append({'segment_id':segment.segment_id, 'lap_id':stored['id'] if stored else None,
                     'ordinal':ordinal if complete else None, 'source_lap':segment.source_lap,
                     'kind':segment.kind, 'label':KINDS.get(segment.kind, segment.kind),
                     'lap_time_s':segment.lap_time_s if complete else None,
                     'observed_duration_s':segment.duration_s, 'sectors_s':sectors,
                     'sector_sources':sources, 'notes':notes, 'eligible':eligible,
                     'exclusion_reason':reason, 'validity':segment.validity})
    eligible = [row for row in rows if row['eligible']]
    times = [row['lap_time_s'] for row in eligible]
    best = min(times) if times else None
    minima, origins = [], []
    for index in range(3):
        candidates = [row for row in eligible if row['sectors_s'][index] is not None]
        value = min((row['sectors_s'][index] for row in candidates), default=None)
        minima.append(value)
        origins.append([row['ordinal'] for row in candidates if abs(row['sectors_s'][index]-value) < 1e-9])
    theoretical = sum(minima) if all(value is not None for value in minima) else None
    for row in rows:
        row['delta_best_s'] = row['lap_time_s']-best if row['eligible'] and best is not None else None
        row['best_sectors'] = [row['eligible'] and value is not None and minima[i] is not None and abs(value-minima[i]) < 1e-9 for i, value in enumerate(row['sectors_s'])]
        row['is_best'] = row['eligible'] and abs(row['lap_time_s']-best) < 1e-9
    return {'rows':rows, 'statistics':{
        'count':len(times), 'excluded_count':len(rows)-len(times),
        'best_s':best, 'average_s':mean(times) if times else None,
        'median_s':median(times) if times else None, 'slowest_s':max(times) if times else None,
        'stddev_s':pstdev(times) if times else None,
        'theoretical_s':theoretical, 'best_sectors_s':minima, 'best_sector_laps':origins,
        'gap_to_theoretical_s':best-theoretical if best is not None and theoretical is not None and best >= theoretical-1e-9 else None},
        'scope':'当前练习内，有已记录圈时且不含维修区状态的完整圈；有效性未核实。残圈不计入平均和理论最快。',
        'sector_method':'S1 使用记录值；S2 = 累计 Sector2 − S1；S3 = 圈时 − 累计 Sector2。逐圈核对分段切换事件，不沿用上一圈计时。'}
