"""Application services independent of HTTP and concrete persistence adapters."""

from collections import OrderedDict, defaultdict
import csv
from datetime import datetime, timezone
from heapq import nsmallest
from io import StringIO
import math
from pathlib import Path
from statistics import mean, median, pstdev
from threading import RLock
from uuid import uuid4

from .alignment import extract_lap
from .cli import summary
from .reader import digest, read_recording
from .storage import BlobStore, SessionRepository
from .timing import timing_summary
from .inventory import inspect_channels
from .trajectory import lap_trajectory
from .conditions import extract_context, context_document, validate_changes
from .track_reference import load_reference
from .comparison import compare_distance, layout_key, share_trajectory_frame
from .pace import analyze_pace, distribution, setup_labels
from .vehicles import normalized, vehicle_brand


MIN_RECORDING_SECONDS = 60
DUPLICATE_IMPORT_MESSAGE = '拒绝导入：相同内容的遥测已存在于档案。'


class ImportRejected(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TelemetryService:
    def __init__(self, repository: SessionRepository, blobs: BlobStore, track_root=None):
        self.repository = repository
        self.blobs = blobs
        self.lock = RLock()
        self.cache = OrderedDict()
        self.context_cache = OrderedDict()
        self.track_root = track_root

    def conditions(self, driver_id, session_id, lap_id=None):
        with self.lock:
            session, recording = self._recording(driver_id, session_id)
            return context_document(session, recording, self._context(driver_id, session, recording),
                                    self.repository.get_annotations(driver_id, session_id), lap_id)

    def _context(self, driver_id, session, recording):
        key = (driver_id, session['id'])
        if key not in self.context_cache:
            with self.blobs.materialize(session['blob_key']) as path:
                self.context_cache[key] = extract_context(path, recording)
            while len(self.context_cache) > 2:
                self.context_cache.popitem(last=False)
        self.context_cache.move_to_end(key)
        return self.context_cache[key]

    def update_conditions(self, driver_id, session_id, payload, lap_id=None):
        with self.lock:
            # Resolve source and lap before mutating; an unreadable source must not produce a partial save.
            self.conditions(driver_id, session_id, lap_id)
            changes = validate_changes(payload, lap_id or 'session')
            self.repository.write_annotations(driver_id, session_id, lap_id or 'session', changes)
            return self.conditions(driver_id, session_id, lap_id)

    def track_reference(self, driver_id, session_id):
        with self.lock:
            session, recording = self._recording(driver_id, session_id)
            return load_reference(self.track_root, self.repository.track_reference_key(driver_id, session_id), recording)

    def _recording(self, driver_id, session_id, session=None):
        if session is None:
            session = self.repository.get_session(driver_id, session_id)
        if session is None:
            raise LookupError("练习记录不存在")
        key = (driver_id, session_id)
        recording = self.cache.get(key)
        if recording is None:
            with self.blobs.materialize(session['blob_key']) as path:
                recording = read_recording(path)
            self._remember(key, recording)
        else:
            self.cache.move_to_end(key)
        return session, recording

    def timing(self, driver_id, session_id):
        with self.lock:
            session, recording = self._recording(driver_id, session_id)
            return timing_summary(recording, session['laps'])

    def pace(self, driver_id, session_id):
        with self.lock:
            session, recording = self._recording(driver_id, session_id)
            result = analyze_pace(recording, session['laps'])
            annotations = self.repository.get_annotations(driver_id, session_id)
            result['setups'] = setup_labels(result['laps'], annotations)
            for stint in result['stints']:
                stint['setups'] = setup_labels(
                    [lap for lap in result['laps'] if lap['stint'] == stint['number']], annotations)
            fields = context_document(session, recording, self._context(driver_id, session, recording), annotations)
            keys = {'fuel', 'ambient', 'track_temp', 'tyres', 'game_version'}
            result['conditions'] = [{'key': item['key'], 'label': item['label'], 'effective': item['effective']}
                                    for item in fields['fields'] if item['key'] in keys]
            return result

    def inventory(self, driver_id, session_id):
        with self.lock:
            session, recording = self._recording(driver_id, session_id)
            with self.blobs.materialize(session['blob_key']) as path:
                return inspect_channels(path, recording)

    def _remember(self, key, recording):
        self.cache[key] = recording
        self.cache.move_to_end(key)
        while len(self.cache) > 2:
            self.cache.popitem(last=False)

    def import_file(self, driver_id: str, path: Path, filename: str):
        with self.lock:
            # 按内容判重，改名后的副本也无需再次解析。
            sha256 = digest(path)
            if self.repository.find_hash(driver_id, sha256):
                raise ImportRejected('duplicate', DUPLICATE_IMPORT_MESSAGE)
            recording = read_recording(path, expected_sha256=sha256)
            duration = recording.clock_s[-1] - recording.clock_s[0]
            if duration < MIN_RECORDING_SECONDS and not math.isclose(
                duration, MIN_RECORDING_SECONDS, rel_tol=0, abs_tol=1e-9
            ):
                raise ImportRejected('recording_too_short',
                                     f'已过滤：录制时长 {duration:.3f} 秒，少于 {MIN_RECORDING_SECONDS} 秒。')
            if not recording.complete_laps:
                raise ImportRejected('no_complete_lap', '已过滤：录制中没有完整圈。')
            session_id, blob_key = str(uuid4()), str(uuid4())
            recording.source_filename = filename
            document = summary(recording)
            self.blobs.commit(path, blob_key)
            try:
                result = self.repository.insert_session(driver_id, session_id, blob_key, filename, document)
                if result is None:
                    raise ImportRejected('duplicate', DUPLICATE_IMPORT_MESSAGE)
            except Exception:
                self.blobs.delete(blob_key)
                raise
            self._remember((driver_id, session_id), recording)
            return result

    def trace(self, driver_id: str, session_id: str, lap_id: str):
        with self.lock:
            session = self.repository.get_session(driver_id, session_id)
            if session is None:
                raise LookupError('练习记录不存在')
            lap = next((item for item in session["laps"] if item["id"] == lap_id), None)
            if lap is None:
                raise LookupError("圈次不存在")
            _, recording = self._recording(driver_id, session_id, session)
            extracted = extract_lap(recording, lap["ordinal"])
            aligned = extracted["aligned"]
            distance = aligned["channels"].get("distance", {}).get("values")
            # A reversal cannot be sorted away: that would misrepresent the lap.
            finite = [value for value in (distance or []) if value is not None]
            distance_available = bool(finite) and all(b >= a for a, b in zip(finite, finite[1:]))
            return {"lap_id": lap_id, "ordinal": lap["ordinal"], "lap_time_s": lap["lap_time_s"],
                    "time_s": aligned["lap_time_s"], "distance_m": distance,
                    "distance_available": distance_available,
                    "channels": {name: data for name, data in aligned["channels"].items() if name != "distance"},
                    "timing": "reconstructed", "validity": "unknown",
                    "trajectory": lap_trajectory(recording, lap['ordinal'])}

    def comparison(self, driver_id, session_id, lap_id, reference_session_id, reference_lap_id):
        with self.lock:
            current = self.repository.get_session(driver_id, session_id)
            reference = self.repository.get_session(driver_id, reference_session_id)
            if current is None or reference is None:
                raise LookupError('录制会话不存在')
            current_layout = layout_key(current['summary']['metadata'])
            reference_layout = layout_key(reference['summary']['metadata'])
            if session_id != reference_session_id and (not all(current_layout) or current_layout != reference_layout):
                raise ValueError('跨会话对比需要两份录制有一致且已知的赛道布局。')
            first = self.trace(driver_id, session_id, lap_id)
            second = first if session_id == reference_session_id and lap_id == reference_lap_id else self.trace(
                driver_id, reference_session_id, reference_lap_id)
            traces = [first, second]
            share_trajectory_frame(traces)
            return {'traces': traces, 'delta': compare_distance(traces)}


def pace_laps(summary):
    return [lap for lap in summary['complete_laps'] if lap['lap_time_s'] is not None and lap['lap_time_s'] > 0
            and not lap.get('contains_pit_state')]


def public_session(row, detail=False):
    data = row["summary"]
    laps = data["complete_laps"]
    times = [lap["lap_time_s"] for lap in laps if lap["lap_time_s"] is not None]
    counted = pace_laps(data)
    best = min(counted, key=lambda lap: lap['lap_time_s'], default=None)
    pace_times = [lap['lap_time_s'] for lap in counted]
    # 直接读取已有目录摘要，历史页无需逐个重新打开 DuckDB。
    pace = {'count': len(counted), 'best_s': best['lap_time_s'] if best else None,
            'best_ordinal': best['complete_lap_number'] if best else None,
            'top5_mean_s': mean(nsmallest(5, pace_times)) if len(pace_times) >= 5 else None,
            'median_s': median(pace_times) if pace_times else None,
            'stddev_s': pstdev(pace_times) if len(pace_times) > 1 else None}
    metadata = data['metadata']
    brand, source = vehicle_brand(metadata, row.get('vehicle_model'), row.get('brand_override'))
    result = {"id": row["id"], "driver_id": row["driver_id"], "filename": row["filename"],
              "created_at": row["created_at"], "metadata": metadata,
              "vehicle_model": row.get('vehicle_model'), "vehicle_brand": brand,
              "vehicle_brand_source": source, "pace": pace,
              "complete_lap_count": len(laps), "best_lap_s": min(times) if times else None,
              "duration_s": data["recording_end_s"]-data["recording_start_s"]}
    if detail:
        by_ordinal = {lap["complete_lap_number"]: lap for lap in laps}
        result.update({"laps": [{**lap, "display_time": by_ordinal[lap["ordinal"]]["recorded_lap_time_display"]}
                                for lap in row["laps"]], "segments": data["segments"],
                       "diagnostics": data["diagnostics"], "catalog": data["catalog"],
                       "available_core_channels": data["available_core_channels"]})
    return result


def recording_date(item):
    value = item['metadata'].get('RecordingTime')
    if value:
        try:
            dt = datetime.fromisoformat(value.replace('_', ':'))
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    return None


def overview_totals(items):
    return {'sessions': len(items), 'complete_laps': sum(item['complete_lap_count'] for item in items),
            'pace_laps': sum(item['pace']['count'] for item in items)}


def session_kind(metadata):
    kind = normalized(metadata.get('SessionType'))
    return 'qualify' if kind == 'qualifying' else kind


def csv_cell(value):
    # 防止录制名称或补录文本在电子表格里被当作公式。
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '＝', '＋', '－', '＠')):
        return "'" + value
    return value


def archive_laps_csv(rows):
    output = StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(('会话编号', '录制时间（UTC）', '录制文件', '赛道', '布局', '会话类型',
                     '品牌', '组别', '车型', '完整圈序号', '源圈号', '官方圈时（秒）',
                     '记录到进站状态', '纳入节奏统计'))
    session_labels = {'practice': '练习', 'qualify': '排位', 'race': '正赛', 'warmup': '热身'}
    for row in rows:
        summary = row['summary']
        metadata = summary['metadata']
        date = recording_date(summary)
        model = row.get('vehicle_model')
        brand, _ = vehicle_brand(metadata, model, row.get('brand_override'))
        session_fields = (row['id'], date.isoformat(timespec='seconds') if date else None, row['filename'],
                          metadata.get('TrackName'), metadata.get('TrackLayout'),
                          session_labels.get(session_kind(metadata), metadata.get('SessionType')),
                          brand, metadata.get('CarClass'), model)
        pace_ordinals = {lap['complete_lap_number'] for lap in pace_laps(summary)}
        for lap in summary['complete_laps']:
            ordinal = lap['complete_lap_number']
            seconds = lap['lap_time_s']
            pit_state = lap.get('contains_pit_state')
            writer.writerow([*(csv_cell(value) for value in session_fields), ordinal, lap.get('source_lap'),
                             f'{seconds:.3f}' if seconds is not None else None,
                             None if pit_state is None else '是' if pit_state else '否',
                             '是' if ordinal in pace_ordinals else '否'])
    return output.getvalue().encode('utf-8-sig')


def overview_breakdown(records):
    groups = defaultdict(list)
    for row, item in records:
        metadata = item['metadata']
        groups[(normalized(item['vehicle_brand']), normalized(metadata.get('CarClass')),
                session_kind(metadata))].append((row, item))
    breakdown = []
    for (brand, category, kind), members in groups.items():
        items = [item for _, item in members]
        sample = items[0]
        # 只从合并后的单圈计时计算节奏，缺少分组的记录计入圈数。
        comparable = bool(brand and category and kind)
        timed = [item for item in items if item['pace']['best_s'] is not None] if comparable else []
        fastest = min(timed, key=lambda item: item['pace']['best_s'], default=None)
        laps = [{'time_s': lap['lap_time_s'], 'ordinal': lap['complete_lap_number']}
                for row, _ in members for lap in pace_laps(row['summary'])] if comparable else []
        breakdown.append({'session_id': sample['id'], 'kind': kind, 'brand': sample['vehicle_brand'],
                          'class': sample['metadata'].get('CarClass'), **overview_totals(items),
                          'pace': distribution(laps),
                          'best_session': fastest['id'] if fastest else None,
                          'best_ordinal': fastest['pace']['best_ordinal'] if fastest else None})
    return sorted(breakdown, key=lambda group: (
        {'race':0, 'qualify':1, 'practice':2, 'warmup':3}.get(group['kind'], 4),
        group['class'] or '', group['brand'] or '\uffff'))


RACE_DURATIONS = (('short', 20 * 60), ('medium', 40 * 60), ('long', 60 * 60), ('endurance', float('inf')))


def race_duration_groups(records):
    buckets = defaultdict(list)
    for row, item in records:
        if session_kind(item['metadata']) == 'race' and item['duration_s'] > 0:
            key = next(key for key, end in RACE_DURATIONS if item['duration_s'] < end)
            buckets[key].append((row, item))
    return {key: overview_breakdown(group) for key, group in buckets.items()}


def catalog_overview(rows):
    items = [public_session(row) for row in rows]
    layouts = defaultdict(list)
    for row, item in zip(rows, items):
        layout = layout_key(item['metadata'])
        # 未知布局只列记录，不与同名赛道的其他记录合并计时。
        key = layout if all(layout) else ('', item['id'])
        layouts[key].append((row, item))
    cards = []
    for records in layouts.values():
        session_items = [item for _, item in records]
        latest = max(session_items, key=lambda item: recording_date(item) or datetime.min.replace(tzinfo=timezone.utc))
        cards.append({'session_id': latest['id'], 'metadata': latest['metadata'], **overview_totals(session_items),
                      'latest_at': latest['metadata'].get('RecordingTime') if recording_date(latest) else None,
                      'groups': overview_breakdown(records), 'race_durations': race_duration_groups(records)})
    cards.sort(key=lambda item: recording_date(item) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return {'items': items, 'overview': {'totals': {**overview_totals(items), 'layouts': len(cards)}, 'layouts': cards}}
