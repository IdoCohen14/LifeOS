"""Internal provider storage/fences; no network or automatic credential copying."""

import json
import re
import secrets
import time

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .account_records import AccountRecords
from .credential_vault import CredentialVault
from .models import AccountMailReview, AccountMoodleChange, AccountProvider, AccountProviderRecord


class AccountProviders(AccountRecords):
    def abort_sync(self, account_id, provider, owner, revision, *, error=None):
        self.validate_provider(provider)
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            row = db.get(AccountProvider, (account_id, provider))
            if row is None or row.lease_owner != owner or row.revision != revision:
                return False
            row.lease_owner, row.lease_until = None, 0
            if error is not None:
                row.error = (
                    error
                    if isinstance(error, str) and re.fullmatch(r"[a-z_]{1,80}", error)
                    else "provider_unavailable"
                )
                row.failures += 1
                row.next_sync = int(time.time()) + min(3600, 60 * 2 ** min(row.failures, 6))
            db.commit()
            return True

    def status(self, account_id, provider):
        self.validate_provider(provider)
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            row = db.get(AccountProvider, (account_id, provider))
            return {
                "configured": bool(row and row.credentials),
                "authorized": bool(row and row.authorized),
                "last_success": row.last_success if row else None,
                "syncing": bool(row and row.lease_owner and row.lease_until > int(time.time())),
                "connected": bool(row and row.last_success is not None and row.error is None),
                "stale": bool(
                    row
                    and row.last_success is not None
                    and (row.error or row.last_success < int(time.time()) - 1800)
                ),
                "error": row.error if row else None,
                "last_attempt": row.last_attempt if row else None,
                "next_sync": row.next_sync if row else 0,
            }

    def __init__(self, engine, directory):
        super().__init__(engine)
        self.vault = CredentialVault(directory)

    def validate_provider(self, provider):
        if provider not in {"google", "gmail", "moodle", "braude"}:
            raise ValueError("Unsupported provider")

    def configure(self, account_id, provider, values, *, expected_revision=None):
        self.validate_provider(provider)
        if not isinstance(values, dict) or len(json.dumps(values).encode()) > 65536:
            raise ValueError("Invalid credentials")
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            row = db.get(AccountProvider, (account_id, provider))
            if expected_revision is not None and (row.revision if row else 0) != expected_revision:
                raise RuntimeError("Provider configuration changed")
            if row is None:
                row = AccountProvider(account_id=account_id, provider=provider, revision=0)
                db.add(row)
            row.credentials = (
                self.vault.encrypt(
                    {"account_id": account_id, "provider": provider, "values": values}
                )
                if values
                else None
            )
            row.revision += 1
            authorization = (
                values.get("url") if provider in {"moodle", "braude"} else values.get("refresh_token")
            )
            row.authorized = isinstance(authorization, str) and bool(authorization)
            if provider == "gmail":
                db.execute(
                    delete(AccountMailReview).where(AccountMailReview.account_id == account_id)
                )
            if provider == "moodle":
                db.execute(
                    delete(AccountMoodleChange).where(AccountMoodleChange.account_id == account_id)
                )
            row.checkpoint, row.lease_owner, row.lease_until, row.last_success = None, None, 0, None
            row.last_attempt, row.error, row.failures, row.next_sync = None, None, 0, 0
            db.execute(
                delete(AccountProviderRecord).where(
                    AccountProviderRecord.account_id == account_id,
                    AccountProviderRecord.provider == provider,
                )
            )
            db.commit()

    def begin_sync(self, account_id, provider):
        self.validate_provider(provider)
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            row = db.get(AccountProvider, (account_id, provider))
            if row is None or row.credentials is None:
                raise ValueError("Provider not configured")
            if row.lease_owner and row.lease_until > int(time.time()):
                raise RuntimeError("Sync in progress")
            decoded = self.vault.decrypt(row.credentials)
            if decoded.get("account_id") != account_id or decoded.get("provider") != provider:
                raise PermissionError("Credential owner mismatch")
            owner = secrets.token_hex(16)
            row.lease_owner, row.lease_until = owner, int(time.time()) + 300
            row.last_attempt = int(time.time())
            result = {
                "owner": owner,
                "revision": row.revision,
                "checkpoint": row.checkpoint,
                "credentials": decoded["values"],
            }
            db.commit()
            return result

    def commit_sync(
        self, account_id, provider, owner, revision, records, checkpoint=None, *, credentials=None
    ):
        self.validate_provider(provider)
        if (
            len(records) > (51000 if provider == "google" else 2000)
            or checkpoint is not None
            and (not isinstance(checkpoint, str) or len(checkpoint) > 4096)
        ):
            raise ValueError("Invalid snapshot")
        staged = {}
        for record in records:
            id = record.get("id")
            if not isinstance(id, str) or not 1 <= len(id) <= 256 or id in staged:
                raise ValueError("Invalid record identity")
            staged[id] = json.dumps({k: v for k, v in record.items() if k != "calendar_text"}, ensure_ascii=False)
        if (
            sum(len(value.encode()) for value in staged.values())
            > (32 if provider == "google" else 16) * 1024 * 1024
        ):
            raise ValueError("Snapshot too large")
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            row = db.get(AccountProvider, (account_id, provider))
            if (
                row is None
                or row.lease_owner != owner
                or row.revision != revision
                or row.lease_until <= int(time.time())
            ):
                raise RuntimeError("Sync ownership lost")
            if provider == "braude":
                from .braude_academic import enrich_events

                records = enrich_events(db, account_id, records)
                staged = {record["id"]: json.dumps(record, ensure_ascii=False) for record in records}
            if provider == "gmail":
                from .mail_calendar import capture

                capture(db, account_id, records)
            if provider == "moodle":
                from .account_moodle_changes import record_changes
                from .moodle_academic import capture
                from .moodle_versions import choose_version

                previous = {record.external_id: json.loads(record.payload) for record in db.scalars(
                    select(AccountProviderRecord).where(AccountProviderRecord.account_id == account_id,
                                                       AccountProviderRecord.provider == "moodle"))}
                records = [choose_version(previous[record["id"]], record) if record["id"] in previous
                           else record for record in records]
                records = capture(db, account_id, records)
                staged = {record["id"]: json.dumps(record, ensure_ascii=False) for record in records}
                record_changes(
                    db, account_id, records, int(time.time()), baseline=row.last_success is None
                )
            db.execute(
                delete(AccountProviderRecord).where(
                    AccountProviderRecord.account_id == account_id,
                    AccountProviderRecord.provider == provider,
                )
            )
            db.add_all(
                AccountProviderRecord(
                    account_id=account_id, provider=provider, external_id=id, payload=value
                )
                for id, value in staged.items()
            )
            row.checkpoint, row.last_success = checkpoint, int(time.time())
            row.error, row.failures, row.next_sync = None, 0, int(time.time()) + 600
            if credentials is not None:
                if (
                    not isinstance(credentials, dict)
                    or len(json.dumps(credentials).encode()) > 65536
                ):
                    raise ValueError("Invalid credentials")
                row.credentials = self.vault.encrypt(
                    {"account_id": account_id, "provider": provider, "values": credentials}
                )
            row.lease_owner, row.lease_until = None, 0
            db.commit()

    def records(self, account_id, provider, *, calendar_only=False):
        self.validate_provider(provider)
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            result = [
                json.loads(row.payload)
                for row in db.scalars(
                    select(AccountProviderRecord).where(
                        AccountProviderRecord.account_id == account_id,
                        AccountProviderRecord.provider == provider,
                    )
                )
            ]
            if provider == "moodle" and calendar_only:
                from .moodle_academic import visible_events

                return visible_events(db, account_id, result)
            return result
