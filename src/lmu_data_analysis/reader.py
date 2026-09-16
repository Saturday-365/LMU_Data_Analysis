"""Read the observed LMU format 1 using explicit physical row ordering."""

from __future__ import annotations

from bisect import bisect_right
import hashlib
import math
from pathlib import Path

import duckdb

from .models import Diagnostic, Recording, Segment, Series, TelemetryError


SAFE_METADATA = {
    "Version", "RecordingTime", "SessionTime", "SessionType", "TrackName",
    "TrackLayout", "WeatherConditions", "CarName", "CarClass",
}
# Source unit is mandatory; no guessed conversions or steering-angle estimates.
CORE_CHANNELS = {
    "speed": ("Ground Speed", "km/h"),
    "throttle": ("Throttle Pos", "%"),
    "brake": ("Brake Pos", "%"),
    "steering": ("Steering Pos", "%"),
    "distance": ("Lap Dist", "m"),
}


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def numeric(value) -> float | int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None


def ordered_values(connection, table: str) -> list:
    rows = connection.execute(f"SELECT rowid,value FROM {quote(table)} ORDER BY rowid").fetchall()
    # Row numbers encode sampling order in this source format. Deleted rows lose time information.
    if [row[0] for row in rows] != list(range(len(rows))):
        raise TelemetryError(f"{table}: non-contiguous source rows; cannot reconstruct time")
    return [row[1] for row in rows]


def event_rows(connection, table: str) -> list[tuple]:
    rows = connection.execute(f"SELECT ts,value FROM {quote(table)} ORDER BY rowid").fetchall()
    if any(numeric(ts) is None for ts, _ in rows):
        raise TelemetryError(f"{table}: missing or non-finite timestamps")
    if any(right[0] <= left[0] for left, right in zip(rows, rows[1:])):
        raise TelemetryError(f"{table}: duplicate or decreasing timestamps")
    return rows


def build_segments(clock, laps, lap_times, pits, diagnostics) -> list[Segment]:
    start, end = clock[0], clock[-1]
    if not laps:
        diagnostics.append(Diagnostic("no_lap_events", "No lap boundaries available"))
        return []
    if any(numeric(v) is None or int(v) != v or v < 0 for _, v in laps):
        raise TelemetryError("Lap: invalid lap counter")
    if any(ts < start-1e-6 or ts > end+1e-6 for ts, _ in laps):
        raise TelemetryError("Lap: event outside recording clock")
    pit_times = [row[0] for row in pits]

    def in_pits_at(time):
        i = bisect_right(pit_times, time)-1
        return i >= 0 and pits[i][1] == 1

    # The first Lap row is an initial state, never evidence of a finish-line crossing.
    boundaries = [(start, int(laps[0][1]), False)]
    for (previous_ts, previous), (ts, counter) in zip(laps, laps[1:]):
        if counter == previous:
            continue
        crossed = counter == previous+1
        if not crossed:
            diagnostics.append(Diagnostic("lap_counter_discontinuity", f"Lap counter changes {previous} -> {counter}"))
        boundaries.append((ts, int(counter), crossed))
    segments = []
    for i, (left, counter, observed_start) in enumerate(boundaries):
        has_end = i+1 < len(boundaries)
        right, next_counter, observed_end = boundaries[i+1] if has_end else (end, counter, False)
        if right <= left:
            continue
        pit_state = in_pits_at(left) or any(left <= ts < right and value == 1 for ts, value in pits)
        full = observed_start and observed_end and next_counter == counter+1
        kind = "complete" if full else "discontinuity"
        if i == 0:
            kind = "out_lap" if pit_state else "leading_fragment"
        elif not has_end:
            kind = "trailing_fragment"
        matched = [(ts, value) for ts, value in lap_times
                   if abs(ts-right) <= 1e-6 and numeric(value) is not None and value > 0]
        official_time = float(matched[-1][1]) if full and matched else None
        if full and official_time is None:
            diagnostics.append(Diagnostic("lap_time_missing", f"No recorded Lap Time at boundary {right}; boundary interval retained separately"))
        if official_time is not None and abs(official_time-(right-left)) > 0.05:
            kind = "timing_mismatch"
            diagnostics.append(Diagnostic("lap_time_mismatch", f"Lap {counter}: recorded time disagrees with boundary interval"))
        segments.append(Segment(len(segments)+1, counter, kind, left, right, official_time,
                                contains_pit_state=pit_state))
    return segments


def _read(connection, path: Path, before: str) -> Recording:
    tables = {}
    for table, column in connection.execute(
        "SELECT c.table_name,c.column_name FROM information_schema.columns c "
        "JOIN information_schema.tables t ON c.table_catalog=t.table_catalog "
        "AND c.table_schema=t.table_schema AND c.table_name=t.table_name "
        "WHERE c.table_schema='main' AND t.table_type='BASE TABLE'"
    ).fetchall():
        tables.setdefault(table, set()).add(column)

    def has(table, columns):
        return set(columns).issubset(tables.get(table, set()))

    for name, cols in {"metadata": ["key", "value"], "channelsList": ["channelName", "frequency", "unit"],
                       "eventsList": ["eventName", "unit"], "GPS Time": ["value"], "Lap": ["ts", "value"]}.items():
        if not has(name, cols):
            raise TelemetryError(f"Unsupported recording: missing {name} or required columns")
    raw_metadata = connection.execute("SELECT key,value FROM metadata").fetchall()
    if len({k for k, _ in raw_metadata}) != len(raw_metadata):
        raise TelemetryError("Duplicate metadata keys")
    metadata = {key: value for key, value in raw_metadata if key in SAFE_METADATA}
    if metadata.get("Version") != "1":
        raise TelemetryError(f"Unsupported recording format Version={metadata.get('Version')!r}; expected '1'")
    channels = connection.execute('SELECT channelName,frequency,unit FROM "channelsList"').fetchall()
    events = connection.execute('SELECT eventName,unit FROM "eventsList"').fetchall()
    if len({row[0] for row in channels}) != len(channels) or len({row[0] for row in events}) != len(events):
        raise TelemetryError("Duplicate channel/event directory entries")
    frequencies = {name: (frequency, unit) for name, frequency, unit in channels}
    event_units = dict(events)
    if "GPS Time" not in frequencies or frequencies["GPS Time"][1] != "s":
        raise TelemetryError("GPS Time: missing frequency or unsupported unit")
    clock_frequency = frequencies["GPS Time"][0]
    if not isinstance(clock_frequency, int) or clock_frequency <= 0:
        raise TelemetryError("GPS Time: invalid frequency")
    clock = ordered_values(connection, "GPS Time")
    if len(clock) < 2 or any(numeric(t) is None for t in clock):
        raise TelemetryError("GPS Time: need at least two finite timestamps")
    if any(not math.isclose(b-a, 1/clock_frequency, abs_tol=1e-6, rel_tol=0)
           for a, b in zip(clock, clock[1:])):
        raise TelemetryError("GPS Time: non-uniform, duplicate or decreasing clock; implicit channel timing is unsafe")
    diagnostics = [Diagnostic("implicit_time_axis", "Continuous times reconstructed from GPS Time and declared frequency; source sampling phase not independently verified")]
    catalog = []
    for name, frequency, unit in channels:
        catalog.append({"source_name": name, "kind": "continuous", "unit": unit,
                        "frequency_hz": frequency, "table_present": name in tables})
    for name, unit in events:
        catalog.append({"source_name": name, "kind": "event", "unit": unit,
                        "frequency_hz": None, "table_present": name in tables})
    series = {}
    for key, (name, unit) in CORE_CHANNELS.items():
        if name not in frequencies or not has(name, ["value"]):
            diagnostics.append(Diagnostic("channel_missing", "Channel unavailable", name))
            continue
        frequency, source_unit = frequencies[name]
        if source_unit != unit:
            diagnostics.append(Diagnostic("unit_unsupported", f"Expected {unit!r}; got {source_unit!r}; no conversion guessed", name))
            continue
        if not isinstance(frequency, int) or frequency <= 0 or clock_frequency % frequency:
            diagnostics.append(Diagnostic("frequency_unsupported", "Frequency is not a positive integer divisor of clock frequency", name))
            continue
        stride = clock_frequency // frequency
        values = ordered_values(connection, name)
        times = clock[::stride]
        if len(values) != len(times):
            diagnostics.append(Diagnostic("sample_count_mismatch", f"Expected {len(times)} rows, found {len(values)}; channel excluded", name))
            continue
        cleaned = [numeric(value) for value in values]
        if any(value is None for value in cleaned):
            diagnostics.append(Diagnostic("missing_values", "NULL/non-finite samples retained as gaps", name))
        series[key] = Series(key, name, unit, "continuous", times, cleaned, frequency,
                             "reconstructed_gps_stride", False)

    def optional_events(name):
        if name not in event_units or not has(name, ["ts", "value"]):
            diagnostics.append(Diagnostic("event_missing", "Event unavailable", name))
            return []
        return event_rows(connection, name)

    # Core boundary events cannot be guessed from the directory or filenames.
    if "Lap" not in event_units:
        raise TelemetryError("Lap missing from event directory")
    lap_rows = event_rows(connection, "Lap")
    lap_times = optional_events("Lap Time")
    if lap_times and event_units["Lap Time"] != "s":
        raise TelemetryError("Lap Time: unsupported unit")
    pits = optional_events("In Pits")
    gear = optional_events("Gear")
    if gear:
        if any(ts < clock[0]-1e-6 or ts > clock[-1]+1e-6 for ts, _ in gear):
            raise TelemetryError("Gear: timestamp outside recording clock")
        values = [numeric(value) for _, value in gear]
        if any(value is not None and (int(value) != value or value < -1) for value in values):
            raise TelemetryError("Gear: invalid discrete value")
        series["gear"] = Series("gear", "Gear", event_units["Gear"], "event",
                                [ts for ts, _ in gear], values, phase_verified=True)
    segments = build_segments(clock, lap_rows, lap_times, pits, diagnostics)
    checks = []
    distance = series.get("distance")
    if distance:
        finite = [value for value in distance.values if value is not None]
        threshold = max(100, (max(finite)-min(finite))*0.5) if finite else 100
        resets = [(distance.times_s[i-1], distance.times_s[i])
                  for i in range(1, len(distance.times_s))
                  if distance.values[i-1] is not None and distance.values[i] is not None
                  and distance.values[i-1]-distance.values[i] > threshold]
        for previous, current in zip(lap_rows, lap_rows[1:]):
            if current[1] == previous[1]+1:
                timestamp = current[0]
                bracket = next(((left, right) for left, right in resets
                                if left-1e-6 <= timestamp <= right+1e-6), None)
                checks.append({"lap_event_s": timestamp, "distance_reset_bracket_s": bracket,
                               "matched": bracket is not None})
        if checks and not all(check["matched"] for check in checks):
            diagnostics.append(Diagnostic("distance_boundary_mismatch", "Distance reset does not bracket a lap event; distance alignment disabled", "Lap Dist"))
            del series["distance"]
    timing_events = {}
    for name in ("Current Sector", "Current Sector1", "Current Sector2", "Last Sector1", "Last Sector2"):
        if name not in event_units or not has(name, ["ts", "value"]):
            continue
        try:
            expected_unit = "" if name == "Current Sector" else "s"
            if event_units[name] != expected_unit:
                raise TelemetryError(f"{name}: unsupported unit")
            rows = event_rows(connection, name)
            if any(ts < clock[0]-1e-6 or ts > clock[-1]+1e-6 for ts, _ in rows):
                raise TelemetryError(f"{name}: timestamp outside recording")
            timing_events[name] = rows
        except TelemetryError as error:
            diagnostics.append(Diagnostic("sector_event_unusable", str(error), name))
    return Recording(path.name, before, metadata, clock, catalog, series, segments, diagnostics, checks, timing_events)


def read_recording(source: str | Path) -> Recording:
    path = Path(source).resolve()
    if not path.is_file():
        raise TelemetryError(f"Telemetry file not found: {path}")
    before = digest(path)
    try:
        with duckdb.connect(str(path), read_only=True, config={
            "enable_external_access": "false", "autoload_known_extensions": "false",
            "autoinstall_known_extensions": "false",
        }) as connection:
            recording = _read(connection, path, before)
    except duckdb.Error as error:
        raise TelemetryError(f"Cannot read telemetry database: {error}") from error
    finally:
        if digest(path) != before:
            raise TelemetryError("Source file changed during reading; result discarded")
    return recording
