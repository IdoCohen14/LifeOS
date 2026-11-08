"""Opt-in offline-only recovery UI; never mounted in the normal application."""

import hashlib
import hmac
import tempfile
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from .recovery import MAGIC, MAX_PACKAGE, RecoveryError, inspect_backup, metadata, restore_backup

ASSETS = Path(__file__).with_name("recovery_ui_assets")


class InspectInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    backup_id: str = Field(max_length=80)
    password: SecretStr = Field(min_length=8, max_length=1024)


class RestoreInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(max_length=80)
    password: SecretStr = Field(min_length=8, max_length=1024)
    confirm: bool


def saved_path(directory, id):
    try:
        if str(UUID(id)) != id:
            raise ValueError()
    except ValueError:
        raise HTTPException(404, "backup_not_found") from None
    folder = directory / "backups"
    path = folder / (id + ".lifeosbackup")
    if (
        folder.resolve() != folder
        or path.is_symlink()
        or path.resolve().parent != folder
        or not path.is_file()
    ):
        raise HTTPException(404, "backup_not_found")
    return path


def fingerprint(path):
    with path.open("rb") as stream:
        raw = stream.read(MAX_PACKAGE + 129)
    if len(raw) > MAX_PACKAGE + 128:
        raise RecoveryError("backup_too_large")
    return hashlib.sha256(raw).hexdigest()


def create_recovery_app(directory, token, *, port=8877, test_mode=False):
    directory = Path(directory).resolve()
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("Recovery capability must be randomly generated")
    origin = f"http://127.0.0.1:{port}"
    started = time.monotonic()
    busy = threading.Lock()
    failures = deque()
    plan = None
    completed = None
    uploaded = None
    upload_folder = None

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if upload_folder is not None:
                upload_folder.cleanup()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def source_path(id):
        if uploaded is not None and uploaded["id"] == id:
            return uploaded["path"]
        return saved_path(directory, id)

    @app.middleware("http")
    async def guards(request, call_next):
        if request.headers.get("host") != f"127.0.0.1:{port}" or (
            request.headers.get("origin") and request.headers["origin"] != origin
        ):
            response = JSONResponse({"detail": "untrusted_origin"}, status_code=403)
        elif request.url.path.startswith("/api/") and (
            time.monotonic() - started >= 1800
            or len(request.headers.get("x-recovery-token", "")) > 1024
            or not hmac.compare_digest(
                request.headers.get("x-recovery-token", "").encode("utf-8"), token.encode("utf-8")
            )
        ):
            response = JSONResponse({"detail": "recovery_session_expired"}, status_code=401)
        elif request.method != "GET" and request.headers.get("origin") != origin:
            response = JSONResponse({"detail": "untrusted_origin"}, status_code=403)
        else:
            response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            }
        )
        return response

    async def body(request, model):
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 8192:
                raise HTTPException(413, "request_too_large")
            raw.extend(chunk)
        try:
            return model.model_validate_json(raw)
        except ValidationError:
            raise HTTPException(422, "invalid_request") from None

    def acquire():
        if not busy.acquire(blocking=False):
            raise HTTPException(409, "recovery_busy")
        while failures and failures[0] <= time.monotonic() - 60:
            failures.popleft()
        if len(failures) >= 5:
            busy.release()
            raise HTTPException(429, "recovery_retry_later")

    def failed(error):
        if isinstance(error, HTTPException):
            raise error
        if isinstance(error, RecoveryError):
            code = str(error)
            if code == "close_lifeos_before_recovery":
                raise HTTPException(409, code) from None
            if code in ("backup_changed", "recovery_preview_expired"):
                raise HTTPException(409, code) from None
            failures.append(time.monotonic())
            raise HTTPException(413 if "large" in code else 422, "backup_invalid") from None
        raise HTTPException(503, "recovery_unavailable") from None

    @app.get("/")
    def page():
        return FileResponse(ASSETS / "index.html", media_type="text/html")

    @app.get("/wizard.js")
    def javascript():
        return FileResponse(ASSETS / "wizard.js", media_type="application/javascript")

    @app.get("/wizard.css")
    def stylesheet():
        return FileResponse(ASSETS / "wizard.css", media_type="text/css")

    @app.get("/api/state")
    def state():
        folder = directory / "backups"
        paths = []
        if folder.exists() and folder.resolve() == folder:
            for index, path in enumerate(folder.glob("*.lifeosbackup")):
                if index >= 1000:
                    raise HTTPException(503, "recovery_list_limit")
                try:
                    paths.append(metadata(saved_path(directory, path.stem)))
                except HTTPException:
                    continue
        return {
            "directory": str(directory),
            "test_mode": test_mode,
            "backups": sorted(paths, key=lambda item: item["created_at"], reverse=True)[:20],
            "completed": completed is not None,
            "max_upload_bytes": MAX_PACKAGE + 128,
        }

    @app.post("/api/upload")
    async def upload(request: Request):
        nonlocal plan, uploaded, upload_folder
        acquire()
        temporary = None
        try:
            if completed is not None:
                raise HTTPException(409, "recovery_completed")
            if request.headers.get("content-type", "").split(";")[0] != "application/octet-stream":
                raise HTTPException(415, "invalid_request")
            name = unquote(request.headers.get("x-backup-name", "selected-backup.lifeosbackup"))
            if not name or len(name) > 240 or any(ord(c) < 32 or c in "/\\" for c in name):
                raise HTTPException(422, "invalid_request")
            plan = None
            directory.parent.mkdir(parents=True, exist_ok=True)
            temporary = tempfile.TemporaryDirectory(
                prefix=".lifeos-recovery-source-", dir=directory.parent
            )
            path = Path(temporary.name) / "selected.lifeosbackup"
            size = 0
            with path.open("xb") as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_PACKAGE + 128:
                        raise HTTPException(413, "backup_too_large")
                    stream.write(chunk)
            with path.open("rb") as stream:
                if stream.read(len(MAGIC)) != MAGIC:
                    raise RecoveryError("backup_invalid")
            old = upload_folder
            upload_folder = temporary
            temporary = None
            uploaded = {"id": str(uuid4()), "name": name, "path": path, "size": size}
            if old is not None:
                old.cleanup()
            return {key: uploaded[key] for key in ("id", "name", "size")}
        except Exception as error:
            if temporary is not None:
                temporary.cleanup()
            failed(error)
        finally:
            busy.release()

    @app.post("/api/inspect")
    async def inspect(request: Request):
        values = await body(request, InspectInput)

        def work():
            nonlocal plan
            acquire()
            try:
                if completed is not None:
                    raise HTTPException(409, "recovery_completed")
                plan = None
                path = source_path(values.backup_id)
                digest = fingerprint(path)
                result = inspect_backup(
                    path, values.password.get_secret_value(), expected_sha256=digest
                )
                plan = {
                    "id": str(uuid4()),
                    "backup_id": values.backup_id,
                    "digest": digest,
                    "expires": time.monotonic() + 600,
                }
                return {
                    "id": plan["id"],
                    "backup_id": values.backup_id,
                    "source_name": uploaded["name"]
                    if uploaded is not None and uploaded["id"] == values.backup_id
                    else path.name,
                    "directory": str(directory),
                    "created_at": result["created_at"],
                    "schema": result["schema"],
                    "counts": {key: result["counts"][key] for key in ("tasks", "events")},
                }
            except Exception as error:
                failed(error)
            finally:
                busy.release()

        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(work)

    @app.post("/api/restore")
    async def restore(request: Request):
        values = await body(request, RestoreInput)
        if not values.confirm:
            raise HTTPException(422, "replacement_confirmation_required")

        def work():
            nonlocal completed
            acquire()
            try:
                if completed is not None:
                    if completed["id"] == values.id:
                        return completed
                    raise HTTPException(409, "recovery_completed")
                if plan is None or plan["id"] != values.id or plan["expires"] <= time.monotonic():
                    raise HTTPException(409, "recovery_preview_expired")
                path = source_path(plan["backup_id"])

                def authorize():
                    if plan["expires"] <= time.monotonic() or time.monotonic() - started >= 1800:
                        raise RecoveryError("recovery_preview_expired")

                result = restore_backup(
                    path,
                    values.password.get_secret_value(),
                    directory,
                    expected_sha256=plan["digest"],
                    authorize=authorize,
                )
                completed = {
                    "id": values.id,
                    "restored": True,
                    "safety_backup_id": result["safety_backup_id"],
                }
                return completed
            except Exception as error:
                failed(error)
            finally:
                busy.release()

        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(work)

    return app
