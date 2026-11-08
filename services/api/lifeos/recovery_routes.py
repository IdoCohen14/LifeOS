import threading
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse

from .backup_inspection import InspectionInput, inspect_saved
from .recovery import RecoveryError, create_backup, export_personal, metadata


def recovery_router(directory, authenticated):
    router = APIRouter(prefix="/recovery", dependencies=[Depends(authenticated)])
    busy = threading.Lock()

    def backups():
        folder = directory / "backups"
        return (
            sorted(
                folder.glob("*.lifeosbackup"), key=lambda path: path.stat().st_mtime, reverse=True
            )[:20]
            if folder.exists()
            else []
        )

    @router.get("/backups")
    def listing():
        return [metadata(path) for path in backups()]

    @router.post("/backups", status_code=201)
    async def create(request: Request):
        try:
            body = await request.json()
            password = body["password"]
        except Exception:
            raise HTTPException(422, "invalid_backup_password") from None
        if not busy.acquire(blocking=False):
            raise HTTPException(409, "recovery_busy")
        try:
            # Run blocking SQLite/KDF work outside the API event loop.
            from starlette.concurrency import run_in_threadpool

            return await run_in_threadpool(create_backup, directory, password)
        except RecoveryError as error:
            raise HTTPException(
                422 if "password" in str(error) else 413 if "large" in str(error) else 503,
                str(error),
            ) from None
        except Exception:
            raise HTTPException(503, "backup_failed") from None
        finally:
            busy.release()

    @router.post("/backups/{id}/inspect")
    async def inspect(id: str, body: InspectionInput):
        if not busy.acquire(blocking=False):
            raise HTTPException(409, "recovery_busy")
        try:
            from starlette.concurrency import run_in_threadpool

            return await run_in_threadpool(
                inspect_saved, directory, id, body.password.get_secret_value()
            )
        except HTTPException:
            raise
        except RecoveryError as error:
            raise HTTPException(
                413 if "large" in str(error) else 422, "backup_inspection_invalid"
            ) from None
        except RuntimeError as error:
            raise HTTPException(
                409 if str(error) == "backup_in_progress" else 503,
                "recovery_busy"
                if str(error) == "backup_in_progress"
                else "backup_inspection_failed",
            ) from None
        except Exception:
            raise HTTPException(503, "backup_inspection_failed") from None
        finally:
            busy.release()

    @router.get("/backups/{id}")
    def download(id: str):
        try:
            if str(UUID(id)) != id:
                raise ValueError()
        except ValueError:
            raise HTTPException(404, "backup_not_found") from None
        path = Path(directory) / "backups" / (id + ".lifeosbackup")
        if not path.is_file():
            raise HTTPException(404, "backup_not_found")
        return FileResponse(
            path, media_type="application/octet-stream", filename="LifeOS-" + id + ".lifeosbackup"
        )

    @router.get("/export")
    def export():
        if not busy.acquire(blocking=False):
            raise HTTPException(409, "recovery_busy")
        try:
            return Response(
                export_personal(directory),
                media_type="application/json",
                headers={
                    "Content-Disposition": 'attachment; filename="LifeOS-personal-export.json"'
                },
            )
        except RecoveryError as error:
            raise HTTPException(413 if "large" in str(error) else 503, str(error)) from None
        except Exception:
            raise HTTPException(503, "export_failed") from None
        finally:
            busy.release()

    return router
