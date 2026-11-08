"""Opt-in unattended encrypted backup using OS-bound credentials and existing format."""

from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import Boolean, Float, Integer, LargeBinary, String, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .assistant import local_instant
from .credential_vault import CredentialVault
from .data_lock import backup_lock
from .db import Base
from .models import Settings
from .recovery import RecoveryError, _create_backup, validate_password


class BackupSchedule(Base):
    __tablename__ = "backup_schedule"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    clock: Mapped[str] = mapped_column(String(5), default="08:00")
    keep: Mapped[int] = mapped_column(Integer, default=7)
    encrypted_password: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_success: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_day: Mapped[str | None] = mapped_column(String, nullable=True)
    last_zone: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)


class AutomaticBackupFile(Base):
    __tablename__ = "automatic_backup_files"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, index=True)


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool
    clock: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    keep: int = Field(ge=1, le=30)
    revision: int = Field(ge=0, le=2147483647)
    password: SecretStr | None = None
    timezone: str = Field(min_length=1, max_length=80)


def current_time():
    return datetime.now(timezone.utc)


def details(row, zone_name):
    return {
        "enabled": bool(row and row.enabled),
        "configured": bool(row and row.encrypted_password),
        "clock": row.clock if row else "08:00",
        "keep": row.keep if row else 7,
        "revision": row.revision if row else 0,
        "timezone": zone_name,
        "last_attempt": row.last_attempt if row else None,
        "last_success": row.last_success if row else None,
        "last_error": row.last_error if row else None,
    }


class ScheduledBackupService:
    def __init__(self, engine, directory):
        self.engine, self.directory = engine, directory
        self.vault = CredentialVault(directory)

    def get(self):
        with Session(self.engine) as db:
            return details(db.get(BackupSchedule, 1), db.get(Settings, 1).timezone)

    def configure(self, body):
        password = body.password.get_secret_value() if body.password else None
        if password is not None:
            try:
                validate_password(password)
            except RecoveryError:
                raise HTTPException(422, "backup_password_minimum_8") from None
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            row = db.get(BackupSchedule, 1)
            if body.revision != (row.revision if row else 0):
                raise HTTPException(409, "backup_schedule_changed")
            zone_name = db.get(Settings, 1).timezone
            if body.timezone != zone_name:
                raise HTTPException(409, "backup_schedule_changed")
            if body.enabled:
                if not password and not (row and row.encrypted_password):
                    raise HTTPException(422, "backup_password_required")
                try:
                    first = current_time().astimezone(ZoneInfo(zone_name)).date()
                    for i in range(371):
                        local_instant(
                            (first + timedelta(days=i)).isoformat(), body.clock, ZoneInfo(zone_name)
                        )
                except ValueError:
                    raise HTTPException(422, "backup_schedule_ambiguous") from None
            if row is None:
                row = BackupSchedule(id=1)
                db.add(row)
            if not body.enabled:
                row.encrypted_password = None
            elif password is not None:
                try:
                    row.encrypted_password = self.vault.encrypt({"password": password})
                except Exception:
                    raise HTTPException(503, "backup_credential_unavailable") from None
            row.enabled, row.clock, row.keep = body.enabled, body.clock, body.keep
            row.revision = body.revision + 1
            row.last_error = None
            # Keep today's successful marker: changing configuration cannot generate a loop.
            db.flush()
            result = details(row, zone_name)
            db.commit()
            return result

    def run_due(self):
        try:
            with backup_lock(self.directory):
                return self._run_locked()
        except RuntimeError:
            return None  # A manual backup or another worker currently owns the slot.

    def _run_locked(self):
        now = current_time().astimezone(timezone.utc)
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            row = db.get(BackupSchedule, 1)
            if not row or not row.enabled or not row.encrypted_password:
                return None
            zone_name = db.get(Settings, 1).timezone
            today = now.astimezone(ZoneInfo(zone_name)).date().isoformat()
            if (row.last_day, row.last_zone) == (today, zone_name):
                return None
            if row.last_attempt is not None and now.timestamp() - row.last_attempt < 900:
                return None
            try:
                due = local_instant(today, row.clock, ZoneInfo(zone_name))
            except ValueError:
                row.last_error = "backup_schedule_ambiguous"
                row.last_attempt = now.timestamp()
                db.commit()
                return None
            if now < due:
                return None
            revision, secret, keep = row.revision, row.encrypted_password, row.keep
            row.last_attempt = now.timestamp()
            db.commit()
        try:
            password = self.vault.decrypt(secret)["password"]
            result = _create_backup(self.directory, password)
        except Exception:
            with Session(self.engine) as db:
                db.execute(text("BEGIN IMMEDIATE"))
                row = db.get(BackupSchedule, 1)
                if row and row.revision == revision:
                    row.last_error = "backup_failed"
                db.commit()
            return None
        try:
            with Session(self.engine) as db:
                db.execute(text("BEGIN IMMEDIATE"))
                db.add(AutomaticBackupFile(id=result["id"], created_at=now.timestamp()))
                row = db.get(BackupSchedule, 1)
                if row:
                    row.last_success = now.timestamp()
                    row.last_day, row.last_zone = today, zone_name
                    if row.revision == revision:
                        row.last_error = None
                db.commit()
        except SQLAlchemyError:
            with Session(self.engine) as db:
                db.execute(text("BEGIN IMMEDIATE"))
                row = db.get(BackupSchedule, 1)
                if row and row.revision == revision:
                    row.last_error = "backup_failed"
                db.commit()
            return None
        # A started run may finish after disable; changed preferences must not authorize deletion.
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            row = db.get(BackupSchedule, 1)
            if row and row.enabled and row.revision == revision:
                old = list(
                    db.scalars(
                        select(AutomaticBackupFile)
                        .order_by(
                            AutomaticBackupFile.created_at.desc(), AutomaticBackupFile.id.desc()
                        )
                        .offset(keep)
                    )
                )
                retention_failed = False
                for item in old:
                    try:
                        if str(UUID(item.id)) != item.id:
                            continue
                        path = self.directory / "backups" / (item.id + ".lifeosbackup")
                        path.unlink(missing_ok=True)
                    except (OSError, ValueError):
                        retention_failed = True
                        continue
                    db.delete(item)
                if retention_failed:
                    row.last_error = "backup_retention_pending"
                db.commit()
        return result


def scheduled_backup_router(engine, directory, authenticated):
    service = ScheduledBackupService(engine, directory)
    router = APIRouter(prefix="/recovery/schedule", dependencies=[Depends(authenticated)])

    @router.get("")
    def get():
        return service.get()

    @router.put("")
    def configure(body: ScheduleInput):
        return service.configure(body)

    return router
