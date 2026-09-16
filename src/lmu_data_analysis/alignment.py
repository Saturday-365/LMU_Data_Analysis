"""Lap data for future charts, with interpolation provenance and explicit gaps."""

from bisect import bisect_left, bisect_right
from dataclasses import asdict
import math

from .models import Recording, Series, TelemetryError, format_lap_time


def continuous_at(times, values, timestamp, max_gap, distance=False):
    right = bisect_left(times, timestamp)
    if right < len(times) and abs(times[right]-timestamp) < 1e-8:
        value = values[right]
        return value, "missing" if value is None else "sample"
    if right == 0 or right == len(times):
        return None, "missing"
    left = right-1
    a, b = values[left], values[right]
    gap = times[right]-times[left]
    if a is None or b is None or gap > max_gap or (distance and b < a-0.01):
        return None, "missing"
    fraction = (timestamp-times[left])/gap
    return a+(b-a)*fraction, "interpolated"


def event_at(series: Series, timestamp):
    index = bisect_right(series.times_s, timestamp)-1
    if index < 0 or series.values[index] is None:
        return None, "missing"
    return series.values[index], "sample" if math.isclose(series.times_s[index], timestamp, abs_tol=1e-8, rel_tol=0) else "held"


def extract_lap(recording: Recording, number: int) -> dict:
    """Select by 1-based complete-lap index, not the source counter or segment ID."""
    if number < 1 or number > len(recording.complete_laps):
        raise TelemetryError(f"Complete lap {number} not available; count={len(recording.complete_laps)}")
    lap = recording.complete_laps[number-1]
    start, end = lap.start_s, lap.end_s
    clock = recording.clock_s
    timestamps = clock[bisect_left(clock, start):bisect_left(clock, end)]
    native, aligned = {}, {}
    for key, series in recording.series.items():
        lo, hi = bisect_left(series.times_s, start), bisect_left(series.times_s, end)
        times, values = series.times_s[lo:hi], series.values[lo:hi]
        item = {"source_name": series.source_name, "unit": series.unit, "kind": series.kind,
                "frequency_hz": series.frequency_hz, "time_basis": series.time_basis,
                "phase_verified": series.phase_verified, "session_time_s": times,
                "lap_time_s": [t-start for t in times], "values": values}
        if series.kind == "event":
            prior = bisect_right(series.times_s, start)-1
            item["state_at_start"] = None if prior < 0 else {
                "event_time_s": series.times_s[prior], "value": series.values[prior]}
            points = [event_at(series, t) for t in timestamps]
        else:
            # Never interpolate using a point from the previous or following lap.
            points = [continuous_at(times, values, t, 1.5/series.frequency_hz, key == "distance")
                      for t in timestamps]
        native[key] = item
        aligned[key] = {"unit": series.unit, "values": [point[0] for point in points],
                        "provenance": [point[1] for point in points]}
    return {"complete_lap_number": number, "segment": asdict(lap),
            "recorded_lap_time_display": format_lap_time(lap.lap_time_s),
            "native": native, "aligned": {"session_time_s": timestamps,
                "lap_time_s": [t-start for t in timestamps], "channels": aligned},
            "notes": ["Continuous timestamps reconstructed; source phase is not independently verified.",
                      "Aligned continuous values interpolate only inside this lap; edges and missing values stay null.",
                      "Gear is held from its preceding event; lap validity remains unknown."]}
