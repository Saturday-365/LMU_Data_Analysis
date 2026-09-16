from __future__ import annotations

from dataclasses import dataclass, field


class TelemetryError(ValueError):
    """A recording cannot safely be interpreted by the current reader."""


@dataclass
class Diagnostic:
    code: str
    message: str
    channel: str | None = None


@dataclass
class Series:
    key: str
    source_name: str
    unit: str
    kind: str
    times_s: list[float]
    values: list[float | int | None]
    frequency_hz: int | None = None
    time_basis: str = "event_timestamp"
    phase_verified: bool = False


@dataclass
class Segment:
    segment_id: int
    source_lap: int
    kind: str
    start_s: float
    end_s: float
    lap_time_s: float | None
    validity: str = "unknown"
    contains_pit_state: bool = False

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class Recording:
    source_filename: str
    source_sha256: str
    metadata: dict[str, str]
    clock_s: list[float]
    catalog: list[dict]
    series: dict[str, Series]
    segments: list[Segment]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    distance_boundary_checks: list[dict] = field(default_factory=list)
    timing_events: dict[str, list[tuple]] = field(default_factory=dict)

    @property
    def complete_laps(self) -> list[Segment]:
        return [segment for segment in self.segments if segment.kind == "complete"]


def format_lap_time(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    milliseconds = int(seconds * 1000 + 0.5)
    minutes, remainder = divmod(milliseconds, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{minutes}:{secs:02d}.{millis:03d}"
