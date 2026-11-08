"""Bounded owner-only logical archives; never copy the shared database or auth keys."""

import base64
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import academic_models, series_models, task_history_models, task_planning_models  # noqa: F401
from .academic_reads import ReadBudget
from .account_preferences import SPECS
from .account_records import AccountRecords
from .assistant import scoped_settings
from .db import Base
from .recovery import derive, metadata, validate_password

MAGIC = b"LIFEOSACCOUNT1\n"
MAX_BYTES = 64 * 1024 * 1024
MAX_ROWS = 100000
CRYPTO_SLOT = BoundedSemaphore(1)


def owned_queries(account_id):
    """Explicit allowlist. Authentication/provider secrets and imported caches are absent."""
    tables = Base.metadata.tables
    tasks, events, terms = (tables[name] for name in ("tasks", "events", "terms"))
    courses, documents, series = (tables[name] for name in ("courses", "documents", "event_series"))
    course_ids = select(courses.c.id).join(terms).where(terms.c.account_id == account_id)
    document_ids = select(documents.c.id).where(documents.c.course_id.in_(course_ids))
    queries = {}
    for name in (
        "tasks",
        "events",
        "terms",
        "event_series",
        "account_preferences",
        "account_conversation_turns",
        "account_notice_states",
        "account_briefings",
        "account_moodle_changes",
    ):
        table = tables[name]
        queries[name] = select(table).where(table.c.account_id == account_id)
    queries["account_preferences"] = queries["account_preferences"].where(
        tables["account_preferences"].c.kind.in_(SPECS)
    )
    queries["courses"] = select(courses).where(courses.c.id.in_(course_ids))
    for name in ("academic_items", "timetable", "grades", "documents"):
        table = tables[name]
        queries[name] = select(table).where(table.c.course_id.in_(course_ids))
    table = tables["document_sections"]
    queries["document_sections"] = select(table).where(table.c.document_id.in_(document_ids))
    table = tables["series_occurrences"]
    queries["series_occurrences"] = (
        select(table)
        .join(series)
        .join(events)
        .where(
            series.c.account_id == account_id,
            events.c.account_id == account_id,
        )
    )
    table = tables["task_time_blocks"]
    queries["task_time_blocks"] = (
        select(table)
        .join(tasks)
        .join(events)
        .where(
            tasks.c.account_id == account_id,
            events.c.account_id == account_id,
        )
    )
    table = tables["task_status_history"]
    queries["task_status_history"] = (
        select(table).join(tasks).where(tasks.c.account_id == account_id)
    )
    return queries


def encode_value(value):
    return {"$bytes": base64.b64encode(value).decode()} if isinstance(value, bytes) else value


class AccountArchive(AccountRecords):
    def __init__(self, engine, directory):
        super().__init__(engine)
        self.directory = Path(directory).resolve()

    def collect(self, db, account_id):
        self.authorize(db, account_id)
        started, count, size = time.monotonic(), 0, 0
        result = {}
        for name, query in owned_queries(account_id).items():
            rows = []
            table = Base.metadata.tables[name]
            for row in (
                db.execute(query.order_by(*table.primary_key.columns)).mappings().yield_per(100)
            ):
                values = {key: encode_value(value) for key, value in row.items()}
                size += len(json.dumps(values, ensure_ascii=False).encode())
                count += 1
                if size > MAX_BYTES or count > MAX_ROWS or time.monotonic() - started > 10:
                    raise ValueError("Account archive resource limit")
                rows.append(values)
            result[name] = rows
        return result

    def export_public(self, account_id):
        with Session(self.engine) as db:
            db.execute(text("BEGIN"))
            self.authorize(db, account_id)
            budget = ReadBudget()
            queries = owned_queries(account_id)
            records = {
                name: [
                    {key: value for key, value in row.items() if key != "account_id"}
                    for row in budget.collect(db.execute(queries[name].limit(10001)).mappings())
                ]
                for name in ("tasks", "events")
            }
            result = {
                "format": "lifeos-personal-export",
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "settings": scoped_settings(db, account_id).model_dump(),
                **records,
            }
            raw = json.dumps(result, ensure_ascii=False).encode()
            if len(raw) > MAX_BYTES:
                raise ValueError("Account export resource limit")
            return raw

    def export(self, account_id):
        with Session(self.engine) as db:
            db.execute(text("BEGIN"))
            tables = self.collect(db, account_id)
        raw = json.dumps(
            {
                "format": "lifeos-account-export",
                "version": 1,
                "account_id": account_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "tables": tables,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        if len(raw) > MAX_BYTES:
            raise ValueError("Account archive resource limit")
        return raw

    def folder(self, account_id):
        if str(UUID(account_id)) != account_id:
            raise ValueError("Invalid account")
        folder = self.directory / "account-backups" / account_id
        if folder.resolve() != folder or folder.is_symlink():
            raise ValueError("Invalid archive directory")
        return folder

    def file(self, account_id, id):
        try:
            if str(UUID(id)) != id:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Invalid archive identity") from None
        path = self.folder(account_id) / (id + ".lifeosaccountbackup")
        if path.is_symlink() or path.resolve().parent != self.folder(account_id):
            raise ValueError("Invalid archive path")
        return path

    def list(self, account_id):
        with Session(self.engine) as db:
            self.authorize(db, account_id)
        folder = self.folder(account_id)
        if not folder.exists():
            return []
        files = []
        for path in folder.glob("*.lifeosaccountbackup"):
            if path.is_file() and not path.is_symlink():
                try:
                    self.file(account_id, path.stem)
                    files.append(metadata(path))
                except ValueError:
                    continue
        return sorted(files, key=lambda row: (row["created_at"], row["id"]), reverse=True)[:100]

    def create(self, account_id, password):
        from .data_lock import account_storage_lock

        with account_storage_lock(self.directory, account_id):
            return self._create_locked(account_id, password)

    def _create_locked(self, account_id, password):
        validate_password(password)
        raw = self.export(account_id)
        if not CRYPTO_SLOT.acquire(blocking=False):
            raise RuntimeError("Archive encryption busy")
        try:
            salt, nonce = os.urandom(16), os.urandom(12)
            header = MAGIC + salt + nonce
            encrypted = header + AESGCM(derive(password, salt)).encrypt(
                nonce, raw, header + account_id.encode()
            )
        finally:
            CRYPTO_SLOT.release()
        # Account may have been disabled while generating the encrypted archive.
        with Session(self.engine) as db:
            self.authorize(db, account_id)
        folder = self.folder(account_id)
        folder.mkdir(parents=True, exist_ok=True)
        target = self.file(account_id, str(uuid4()))
        partial = target.with_suffix(".partial")
        try:
            with partial.open("xb") as file:
                os.chmod(partial, 0o600)
                file.write(encrypted)
                file.flush()
                os.fsync(file.fileno())
            os.replace(partial, target)
        finally:
            partial.unlink(missing_ok=True)
        return metadata(target)

    def read(self, account_id, id, password):
        with Session(self.engine) as db:
            self.authorize(db, account_id)
        path = self.file(account_id, id)
        if not path.is_file():
            raise LookupError("Account archive not found")
        if path.stat().st_size > MAX_BYTES + 128:
            raise ValueError("Account archive resource limit")
        raw = path.read_bytes()
        length = len(MAGIC)
        if len(raw) < length + 44 or not raw.startswith(MAGIC):
            raise ValueError("Invalid account archive")
        if not CRYPTO_SLOT.acquire(blocking=False):
            raise RuntimeError("Archive encryption busy")
        try:
            header, salt, nonce = (
                raw[: length + 28],
                raw[length : length + 16],
                raw[length + 16 : length + 28],
            )
            payload = AESGCM(derive(password, salt)).decrypt(
                nonce, raw[length + 28 :], header + account_id.encode()
            )
            data = json.loads(payload)
            if (
                data["format"] != "lifeos-account-export"
                or data["version"] != 1
                or data["account_id"] != account_id
                or not isinstance(data["tables"], dict)
                or set(data["tables"]) != set(owned_queries(account_id))
                or any(not isinstance(rows, list) for rows in data["tables"].values())
            ):
                raise ValueError()
            return data
        except Exception:
            raise ValueError("Invalid account archive or password") from None
        finally:
            CRYPTO_SLOT.release()

    def inspect(self, account_id, id, password):
        data = self.read(account_id, id, password)
        return {
            "id": id,
            "created_at": data["created_at"],
            "counts": {name: len(rows) for name, rows in data["tables"].items()},
            "reconnect_required": True,
        }
