"""Read-only inspection of an existing local encrypted backup, never online restore."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .data_lock import backup_lock
from .recovery import RecoveryError, inspect_backup


class InspectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    password: SecretStr = Field(min_length=8, max_length=1024)


def inspect_saved(directory, id, password):
    try:
        if str(UUID(id)) != id:
            raise ValueError()
    except ValueError:
        raise HTTPException(404, "backup_not_found") from None
    directory = Path(directory).resolve()
    with backup_lock(directory):
        folder = directory / "backups"
        path = folder / (id + ".lifeosbackup")
        if path.resolve().parent != folder or not path.is_file() or path.is_symlink():
            raise HTTPException(404, "backup_not_found")
        try:
            result = inspect_backup(path, password)
        except sqlite3.DatabaseError as error:
            if (getattr(error, "sqlite_errorcode", 0) & 255) in (
                sqlite3.SQLITE_ERROR,
                sqlite3.SQLITE_CORRUPT,
                sqlite3.SQLITE_SCHEMA,
                sqlite3.SQLITE_FORMAT,
                sqlite3.SQLITE_NOTADB,
            ):
                raise RecoveryError("invalid_backup") from None
            raise
        try:
            created = datetime.fromisoformat(result["created_at"].replace("Z", "+00:00"))
            if created.utcoffset() is None:
                raise ValueError()
        except (ValueError, TypeError):
            raise RecoveryError("invalid_backup") from None
        return {
            "valid": True,
            "created_at": created.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "schema": result["schema"],
            "counts": {key: result["counts"][key] for key in ("tasks", "events")},
        }
