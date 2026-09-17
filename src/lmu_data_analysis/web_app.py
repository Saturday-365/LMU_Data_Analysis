"""Local-only HTTP adapter. Replace identity and persistence before cloud deployment."""

from pathlib import Path, PureWindowsPath
import sqlite3
from typing import Protocol
from urllib.parse import unquote, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware

from .models import TelemetryError
from .storage import LocalBlobStore, SQLiteSessionRepository
from .web_service import TelemetryService, public_session

ROOT = Path(__file__).resolve().parents[2]
LOCAL_DRIVER_ID = "b9919ff0-6e03-4a15-91dc-68f58ee21516"


class IdentityProvider(Protocol):
    def current_driver(self, request: Request) -> str: ...


class LocalIdentity:
    def current_driver(self, request):
        # Never accept a driver ID supplied by the browser.
        return LOCAL_DRIVER_ID


def create_app(data_dir=None, *, identity=None, repository=None, blobs=None, max_upload_bytes=128*1024*1024):
    directory = Path(data_dir or ROOT / "data")
    repository = repository or SQLiteSessionRepository(directory / "catalog.sqlite3")
    blobs = blobs or LocalBlobStore(directory / "recordings")
    identity = identity or LocalIdentity()
    service = TelemetryService(repository, blobs, directory / 'track-resources')
    app = FastAPI(title="LMU Data Analysis", version="0.2.0-local", docs_url=None, redoc_url=None)
    app.state.service = service
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def local_boundary(request, call_next):
        hostname = urlsplit(str(request.url)).hostname
        if hostname not in {"127.0.0.1", "localhost", "testserver"}:
            return JSONResponse({"detail": "此版本仅供本机运行"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "不允许跨站访问本地数据"}, status_code=403)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.headers.get("x-lmu-client") != "web":
            return JSONResponse({"detail": "缺少本地客户端标识"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        response.headers["Cache-Control"] = "no-store"
        return response

    def driver(request):
        driver_id = identity.current_driver(request)
        return repository.ensure_driver(driver_id, "本地车手")

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "mode": "local", "api_version": "v1"}

    @app.get("/api/v1/me")
    def me(request: Request):
        return {**driver(request), "mode": "local"}

    @app.get("/api/v1/sessions")
    def sessions(request: Request):
        return {"items": [public_session(row) for row in repository.list_sessions(driver(request)["id"])]}

    @app.get("/api/v1/sessions/{session_id}")
    def session_detail(session_id: str, request: Request):
        row = repository.get_session(driver(request)["id"], session_id)
        if row is None:
            raise HTTPException(404, "练习记录不存在")
        return public_session(row, True)

    @app.post("/api/v1/sessions", status_code=201)
    async def import_session(request: Request):
        owner = driver(request)["id"]
        filename = PureWindowsPath(unquote(request.headers.get("x-filename", "recording.duckdb"))).name
        if not filename.lower().endswith(".duckdb") or len(filename) > 240:
            raise HTTPException(400, "请选择 LMU 原生 .duckdb 文件")
        staging = blobs.new_staging()
        size = 0
        try:
            with staging.open("xb") as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > max_upload_bytes:
                        raise HTTPException(413, "文件超过本地版本的 128 MB 上限")
                    stream.write(chunk)
            if size == 0:
                raise HTTPException(400, "文件为空")
            row, duplicate = await run_in_threadpool(service.import_file, owner, staging, filename)
            return JSONResponse({"session": public_session(row, True), "duplicate": duplicate},
                                status_code=200 if duplicate else 201)
        except TelemetryError as error:
            message = str(error).replace(str(staging), "所选文件")
            raise HTTPException(422, f"无法解析遥测：{message}") from error
        except OSError as error:
            raise HTTPException(500, "本地存储失败，请检查磁盘空间和目录权限") from error
        finally:
            if staging.is_file():
                staging.unlink()

    @app.get("/api/v1/sessions/{session_id}/laps/{lap_id}/trace")
    def trace(session_id: str, lap_id: str, request: Request):
        try:
            return service.trace(driver(request)["id"], session_id, lap_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except (TelemetryError, OSError) as error:
            raise HTTPException(422, "该记录无法读取，请检查本地文件或重新导入") from error

    @app.get("/api/v1/sessions/{session_id}/timing")
    def timing(session_id: str, request: Request):
        try:
            return service.timing(driver(request)['id'], session_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except (TelemetryError, OSError) as error:
            raise HTTPException(422, "无法读取圈速信息，请检查原始文件") from error

    @app.get("/api/v1/sessions/{session_id}/inventory")
    def inventory(session_id: str, request: Request):
        try:
            return service.inventory(driver(request)['id'], session_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except (TelemetryError, OSError) as error:
            raise HTTPException(422, "无法读取数据目录，请检查原始文件") from error

    @app.get('/api/v1/sessions/{session_id}/conditions')
    def conditions(session_id: str, request: Request, lap_id: str | None = None):
        try:
            return service.conditions(driver(request)['id'], session_id, lap_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except (TelemetryError, OSError) as error:
            raise HTTPException(422, '无法读取练习信息') from error

    @app.patch('/api/v1/sessions/{session_id}/conditions')
    async def edit_conditions(session_id: str, request: Request, lap_id: str | None = None):
        try:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 128*1024:
                    raise HTTPException(413, '练习信息过大')
            import json
            payload = json.loads(body)
            return await run_in_threadpool(service.update_conditions, driver(request)['id'], session_id, payload, lap_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except TelemetryError as error:
            raise HTTPException(422, '无法读取练习信息') from error
        except (ValueError, UnicodeError) as error:
            raise HTTPException(422, str(error)) from error
        except (OSError, sqlite3.Error) as error:
            raise HTTPException(500, '保存失败，请检查本地存储；原始遥测未修改') from error

    @app.get('/api/v1/sessions/{session_id}/track-reference')
    def track_reference(session_id: str, request: Request):
        try:
            return service.track_reference(driver(request)['id'], session_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except (TelemetryError, OSError) as error:
            raise HTTPException(422, '无法读取赛道参照') from error

    web_root = ROOT / "web"
    app.mount("/assets", StaticFiles(directory=web_root), name="assets")

    @app.get("/")
    def index():
        return FileResponse(web_root / "index.html")

    return app
