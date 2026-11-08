"""Opt-in account archive scheduling with owner-bound secrets and scoped retention."""

import base64
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .account_archive import AccountArchive
from .assistant import local_instant, scoped_settings
from .credential_vault import CredentialVault
from .models import AccountPreference
from .recovery import validate_password
from .scheduled_backups import ScheduleInput


class AccountBackupSchedule(AccountArchive):
    def __init__(self, engine, directory):
        super().__init__(engine, directory)
        self.vault = CredentialVault(directory)

    def load(self, db, account_id):
        row = db.get(AccountPreference, (account_id, "backup_schedule"))
        return row, json.loads(row.payload) if row else {
            "enabled": False,
            "clock": "08:00",
            "keep": 7,
            "secret": None,
            "last_attempt": None,
            "last_success": None,
            "last_error": None,
            "last_day": None,
            "last_zone": None,
            "files": [],
        }

    def get(self, account_id):
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            row, state = self.load(db, account_id)
            return {
                **{
                    key: state[key]
                    for key in (
                        "enabled",
                        "clock",
                        "keep",
                        "last_attempt",
                        "last_success",
                        "last_error",
                    )
                },
                "configured": bool(state["secret"]),
                "revision": row.revision if row else 0,
                "timezone": scoped_settings(db, account_id).timezone,
            }

    def configure(self, account_id, values, *, now=None):
        body = ScheduleInput.model_validate(values)
        now = now or datetime.now(timezone.utc)
        password = body.password.get_secret_value() if body.password else None
        if password is not None:
            validate_password(password)
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            row, state = self.load(db, account_id)
            zone_name = scoped_settings(db, account_id).timezone
            if body.revision != (row.revision if row else 0) or body.timezone != zone_name:
                raise ValueError("Backup schedule changed")
            if body.enabled:
                if not password and not state["secret"]:
                    raise ValueError("Backup password required")
                day = now.astimezone(ZoneInfo(zone_name)).date()
                for offset in range(371):
                    local_instant(
                        (day + timedelta(days=offset)).isoformat(), body.clock, ZoneInfo(zone_name)
                    )
                if password is not None:
                    state["secret"] = base64.b64encode(
                        self.vault.encrypt(
                            {
                                "account_id": account_id,
                                "password": password,
                            }
                        )
                    ).decode()
            else:
                state["secret"] = None
            state.update(enabled=body.enabled, clock=body.clock, keep=body.keep, last_error=None)
            if row is None:
                row = AccountPreference(account_id=account_id, kind="backup_schedule", revision=0)
                db.add(row)
            row.revision += 1
            row.payload = json.dumps(state)
            db.commit()
        return self.get(account_id)

    def run_due(self, account_id, *, now=None):
        now = now or datetime.now(timezone.utc)
        if now.utcoffset() is None:
            raise ValueError("UTC offset required")
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            row, state = self.load(db, account_id)
            if not row or not state["enabled"] or not state["secret"]:
                return None
            zone_name = scoped_settings(db, account_id).timezone
            day = now.astimezone(ZoneInfo(zone_name)).date().isoformat()
            if (
                (state["last_day"], state["last_zone"]) == (day, zone_name)
                or state["last_attempt"] is not None
                and now.timestamp() - state["last_attempt"] < 900
            ):
                return None
            try:
                due = local_instant(day, state["clock"], ZoneInfo(zone_name))
            except ValueError:
                state.update(last_error="backup_schedule_ambiguous", last_attempt=now.timestamp())
                row.payload = json.dumps(state)
                db.commit()
                return None
            if now < due:
                return None
            revision, secret = row.revision, state["secret"]
            state["last_attempt"] = now.timestamp()
            row.payload = json.dumps(state)
            db.commit()
        try:
            envelope = self.vault.decrypt(base64.b64decode(secret, validate=True))
            if envelope.get("account_id") != account_id:
                raise ValueError("Backup owner mismatch")
            result = self.create(account_id, envelope["password"])
        except Exception:
            with Session(self.engine) as db:
                begin_academic_write(db)
                self.authorize(db, account_id)
                row, current = self.load(db, account_id)
                if row and row.revision == revision:
                    current["last_error"] = "backup_failed"
                    row.payload = json.dumps(current)
                    db.commit()
            return None
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            row, current = self.load(db, account_id)
            if row is None:
                return result
            current["files"].append(result["id"])
            current.update(last_success=now.timestamp(), last_day=day, last_zone=zone_name)
            if row.revision == revision:
                current["last_error"] = None
                if current["enabled"]:
                    keep = current["keep"]
                    retained = []
                    for id in current["files"][:-keep]:
                        try:
                            self.file(account_id, id).unlink(missing_ok=True)
                        except (OSError, ValueError):
                            retained.append(id)
                            current["last_error"] = "backup_retention_pending"
                    current["files"] = retained + current["files"][-keep:]
            row.payload = json.dumps(current)
            db.commit()
        return result
