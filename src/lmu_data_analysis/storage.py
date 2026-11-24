"""Persistence ports and local adapters. IDs, ownership and blobs are separate."""

from contextlib import contextmanager, closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Protocol
from uuid import UUID, uuid4


class SessionRepository(Protocol):
    def get_annotations(self, driver_id: str, session_id: str) -> list[dict]: ...
    def write_annotations(self, driver_id: str, session_id: str, scope: str, changes: dict) -> None: ...
    def track_reference_key(self, driver_id: str, session_id: str) -> str | None: ...
    def ensure_driver(self, driver_id: str, name: str) -> dict: ...
    def list_sessions(self, driver_id: str) -> list[dict]: ...
    def get_session(self, driver_id: str, session_id: str) -> dict | None: ...
    def find_hash(self, driver_id: str, sha256: str) -> dict | None: ...
    def list_intervals(self, driver_id: str, layout: tuple[str, str]) -> list[dict]: ...
    def save_interval(self, driver_id: str, layout: tuple[str, str], values: dict,
                      interval_id: str | None = None) -> dict: ...
    def delete_interval(self, driver_id: str, layout: tuple[str, str], interval_id: str) -> None: ...
    def insert_session(self, driver_id: str, session_id: str, blob_key: str,
                       filename: str, summary: dict) -> dict: ...


class BlobStore(Protocol):
    def new_staging(self) -> Path: ...
    def commit(self, staging: Path, key: str) -> None: ...
    def delete(self, key: str) -> None: ...
    @contextmanager
    def materialize(self, key: str): ...


class LocalBlobStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Keys originate on the server, never from an uploaded filename or path.
        return self.root / (str(UUID(key)) + ".duckdb")

    def new_staging(self) -> Path:
        return self.root / (str(uuid4()) + ".upload")

    def commit(self, staging: Path, key: str) -> None:
        staging.replace(self._path(key))

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    @contextmanager
    def materialize(self, key: str):
        # A future object-store adapter can download to a temporary local file here.
        yield self._path(key)


class SQLiteSessionRepository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connection() as c:
            version = c.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise RuntimeError(f"Unsupported catalog schema version {version}")
            if version == 0:
                c.executescript("""
                    CREATE TABLE drivers(id TEXT PRIMARY KEY, display_name TEXT NOT NULL);
                    CREATE TABLE sessions(
                        id TEXT PRIMARY KEY, driver_id TEXT NOT NULL REFERENCES drivers(id),
                        blob_key TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
                        sha256 TEXT NOT NULL, created_at TEXT NOT NULL, summary_json TEXT NOT NULL,
                        UNIQUE(driver_id, sha256));
                    CREATE INDEX session_owner ON sessions(driver_id,created_at);
                    CREATE TABLE laps(
                        id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                        ordinal INTEGER NOT NULL, source_lap INTEGER NOT NULL,
                        lap_time_s REAL, validity TEXT NOT NULL,
                        UNIQUE(session_id,ordinal));
                    PRAGMA user_version=1;
                """)
            if version < 2:
                if version == 1:
                    # SQLite's backup API includes committed WAL data. Never overwrite an earlier backup.
                    backup = path.with_name(path.name + '.pre-v2-' + uuid4().hex + '.bak')
                    with closing(sqlite3.connect(backup)) as destination:
                        c.backup(destination)
                # Explicit transaction: executescript would commit before running its statements.
                c.execute('BEGIN IMMEDIATE')
                c.execute('CREATE TABLE annotations(session_id TEXT NOT NULL REFERENCES sessions(id), '
                          'scope TEXT NOT NULL, field TEXT NOT NULL, value_json TEXT NOT NULL, '
                          'updated_at TEXT NOT NULL, PRIMARY KEY(session_id,scope,field))')
                c.execute('CREATE TABLE track_references(session_id TEXT PRIMARY KEY REFERENCES sessions(id), '
                          'resource_key TEXT NOT NULL)')
                c.execute('PRAGMA user_version=2')
            # 区间库是独立的附加表，旧版仍可使用同一份会话目录。
            c.execute("""CREATE TABLE IF NOT EXISTS analysis_intervals (
                id TEXT PRIMARY KEY,
                driver_id TEXT NOT NULL REFERENCES drivers(id),
                track_name TEXT NOT NULL,
                track_layout TEXT NOT NULL,
                name TEXT NOT NULL COLLATE NOCASE,
                start_m REAL NOT NULL,
                end_m REAL NOT NULL CHECK (start_m >= 0 AND start_m < end_m),
                UNIQUE(driver_id, track_name, track_layout, name)
            )""")

    @contextmanager
    def connection(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            with c:
                yield c
        finally:
            c.close()

    def ensure_driver(self, driver_id: str, name: str) -> dict:
        with self.connection() as c:
            c.execute("INSERT OR IGNORE INTO drivers VALUES (?,?)", (driver_id, name))
            return dict(c.execute("SELECT * FROM drivers WHERE id=?", (driver_id,)).fetchone())

    def get_annotations(self, driver_id, session_id):
        if self.get_session(driver_id, session_id) is None:
            raise LookupError('练习记录不存在')
        with self.connection() as c:
            return [{**dict(row), 'data': json.loads(row['value_json'])} for row in c.execute(
                'SELECT * FROM annotations WHERE session_id=?', (session_id,))]

    def write_annotations(self, driver_id, session_id, scope, changes):
        session = self.get_session(driver_id, session_id)
        if session is None:
            raise LookupError('练习记录不存在')
        if scope != 'session' and scope not in {lap['id'] for lap in session['laps']}:
            raise LookupError('圈次不存在')
        with self.connection() as c:
            for field, data in changes.items():
                if data is None:
                    c.execute('DELETE FROM annotations WHERE session_id=? AND scope=? AND field=?',
                              (session_id, scope, field))
                else:
                    c.execute('INSERT INTO annotations VALUES (?,?,?,?,?) ON CONFLICT(session_id,scope,field) '
                              'DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at',
                              (session_id, scope, field, json.dumps(data, ensure_ascii=False),
                               datetime.now(timezone.utc).isoformat()))

    def track_reference_key(self, driver_id, session_id):
        if self.get_session(driver_id, session_id) is None:
            raise LookupError('练习记录不存在')
        with self.connection() as c:
            row = c.execute('SELECT resource_key FROM track_references WHERE session_id=?', (session_id,)).fetchone()
            return row[0] if row else None

    def list_intervals(self, driver_id, layout):
        with self.connection() as c:
            return [dict(row) for row in c.execute(
                'SELECT id, name, start_m, end_m FROM analysis_intervals '
                'WHERE driver_id=? AND track_name=? AND track_layout=? ORDER BY start_m,end_m,name',
                (driver_id, *layout))]

    def save_interval(self, driver_id, layout, values, interval_id=None):
        parameters = (values['name'], values['start_m'], values['end_m'])
        with self.connection() as c:
            if interval_id is None:
                row = c.execute(
                    'INSERT INTO analysis_intervals VALUES (?,?,?,?,?,?,?) RETURNING id,name,start_m,end_m',
                    (str(uuid4()), driver_id, *layout, *parameters)).fetchone()
            else:
                row = c.execute(
                    'UPDATE analysis_intervals SET name=?,start_m=?,end_m=? '
                    'WHERE driver_id=? AND track_name=? AND track_layout=? AND id=? RETURNING id,name,start_m,end_m',
                    (*parameters, driver_id, *layout, interval_id)).fetchone()
            if row is None:
                raise LookupError('区间不存在')
            return dict(row)

    def delete_interval(self, driver_id, layout, interval_id):
        with self.connection() as c:
            deleted = c.execute(
                'DELETE FROM analysis_intervals WHERE driver_id=? AND track_name=? AND track_layout=? AND id=?',
                (driver_id, *layout, interval_id))
            if not deleted.rowcount:
                raise LookupError('区间不存在')

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        result = dict(row)
        result["summary"] = json.loads(result.pop("summary_json"))
        model = json.loads(result.pop('model_annotation', None) or 'null')
        result['vehicle_model'] = model['value'] if model and model['state'] == 'known' else None
        return result

    def list_sessions(self, driver_id):
        with self.connection() as c:
            return [self._decode(row) for row in c.execute(
                "SELECT s.*, a.value_json AS model_annotation FROM sessions s LEFT JOIN annotations a "
                "ON a.session_id=s.id AND a.scope='session' AND a.field='model' "
                "WHERE s.driver_id=? ORDER BY s.created_at DESC,s.id DESC", (driver_id,))]

    def get_session(self, driver_id, session_id):
        with self.connection() as c:
            result = self._decode(c.execute(
                "SELECT s.*, a.value_json AS model_annotation FROM sessions s LEFT JOIN annotations a "
                "ON a.session_id=s.id AND a.scope='session' AND a.field='model' "
                "WHERE s.driver_id=? AND s.id=?", (driver_id, session_id)).fetchone())
            if result:
                result["laps"] = [dict(row) for row in c.execute(
                    "SELECT * FROM laps WHERE session_id=? ORDER BY ordinal", (session_id,))]
            return result

    def find_hash(self, driver_id, sha256):
        with self.connection() as c:
            return self._decode(c.execute("SELECT * FROM sessions WHERE driver_id=? AND sha256=?",
                                         (driver_id, sha256)).fetchone())

    def insert_session(self, driver_id, session_id, blob_key, filename, summary):
        with self.connection() as c:
            c.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?)", (
                session_id, driver_id, blob_key, filename, summary["source_sha256"],
                datetime.now(timezone.utc).isoformat(), json.dumps(summary, ensure_ascii=False)))
            c.executemany("INSERT INTO laps VALUES (?,?,?,?,?,?)", [
                (str(uuid4()), session_id, lap["complete_lap_number"], lap["source_lap"],
                 lap["lap_time_s"], lap["validity"]) for lap in summary["complete_laps"]])
        return self.get_session(driver_id, session_id)
