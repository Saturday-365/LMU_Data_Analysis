"""Application services independent of HTTP and concrete persistence adapters."""

from collections import OrderedDict
from pathlib import Path
from threading import RLock
from uuid import uuid4

from .alignment import extract_lap
from .cli import summary
from .reader import read_recording
from .storage import BlobStore, SessionRepository
from .timing import timing_summary
from .inventory import inspect_channels
from .trajectory import lap_trajectory
from .conditions import extract_context, context_document, validate_changes
from .track_reference import load_reference


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
            key = (driver_id, session_id)
            if key not in self.context_cache:
                with self.blobs.materialize(session['blob_key']) as path:
                    self.context_cache[key] = extract_context(path, recording)
                while len(self.context_cache) > 2:
                    self.context_cache.popitem(last=False)
            self.context_cache.move_to_end(key)
            return context_document(session, recording, self.context_cache[key],
                                    self.repository.get_annotations(driver_id, session_id), lap_id)

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

    def _recording(self, driver_id, session_id):
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
            recording = read_recording(path)
            existing = self.repository.find_hash(driver_id, recording.source_sha256)
            if existing:
                return self.repository.get_session(driver_id, existing["id"]), True
            session_id, blob_key = str(uuid4()), str(uuid4())
            recording.source_filename = filename
            document = summary(recording)
            self.blobs.commit(path, blob_key)
            try:
                result = self.repository.insert_session(driver_id, session_id, blob_key, filename, document)
            except Exception:
                self.blobs.delete(blob_key)
                raise
            self._remember((driver_id, session_id), recording)
            return result, False

    def trace(self, driver_id: str, session_id: str, lap_id: str):
        with self.lock:
            session = self.repository.get_session(driver_id, session_id)
            if session is None:
                raise LookupError("练习记录不存在")
            lap = next((item for item in session["laps"] if item["id"] == lap_id), None)
            if lap is None:
                raise LookupError("圈次不存在")
            key = (driver_id, session_id)
            recording = self.cache.get(key)
            if recording is None:
                with self.blobs.materialize(session["blob_key"]) as path:
                    recording = read_recording(path)
                self._remember(key, recording)
            else:
                self.cache.move_to_end(key)
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


def public_session(row, detail=False):
    data = row["summary"]
    laps = data["complete_laps"]
    times = [lap["lap_time_s"] for lap in laps if lap["lap_time_s"] is not None]
    result = {"id": row["id"], "driver_id": row["driver_id"], "filename": row["filename"],
              "created_at": row["created_at"], "metadata": data["metadata"],
              "complete_lap_count": len(laps), "best_lap_s": min(times) if times else None,
              "duration_s": data["recording_end_s"]-data["recording_start_s"]}
    if detail:
        by_ordinal = {lap["complete_lap_number"]: lap for lap in laps}
        result.update({"laps": [{**lap, "display_time": by_ordinal[lap["ordinal"]]["recorded_lap_time_display"]}
                                for lap in row["laps"]], "segments": data["segments"],
                       "diagnostics": data["diagnostics"], "catalog": data["catalog"],
                       "available_core_channels": data["available_core_channels"]})
    return result
