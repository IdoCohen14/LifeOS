"""Reviewed same-account logical restore, with safety archive and atomic replacement."""

import base64
import hashlib
import json
import math
import time
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import Boolean, Float, Integer, LargeBinary, delete, insert, select, tuple_
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .academic_calendar import slot_occurrences
from .academic_schemas import CourseInput, GradeInput, ItemInput, SlotInput, TermInput
from .account_archive import MAX_BYTES, MAX_ROWS, AccountArchive, owned_queries
from .account_preferences import SPECS
from .accounts import require_account_session
from .db import Base
from .models import AccountPreference, AccountProvider, LoginSession
from .schemas import EventInput, TaskInput
from .security import token_hash

ORDER = (
    "tasks",
    "events",
    "terms",
    "courses",
    "event_series",
    "academic_items",
    "timetable",
    "grades",
    "documents",
    "document_sections",
    "series_occurrences",
    "task_time_blocks",
    "account_preferences",
    "account_conversation_turns",
    "account_notice_states",
    "account_briefings",
    "account_moodle_changes",
    "task_status_history",
)


def digest(tables):
    return hashlib.sha256(
        json.dumps(tables, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_tables(account_id, tables):
    """Reject cross-owner links and malformed values before touching the live database."""
    if set(tables) != set(ORDER) or sum(len(rows) for rows in tables.values()) > MAX_ROWS:
        raise ValueError("Invalid archive tables")
    prepared, identities = {}, {}
    schemas = {
        "tasks": TaskInput,
        "events": EventInput,
        "terms": TermInput,
        "courses": CourseInput,
        "academic_items": ItemInput,
        "timetable": SlotInput,
        "grades": GradeInput,
    }
    started = time.monotonic()
    for name in ORDER:
        table = Base.metadata.tables[name]
        rows, keys = [], set()
        for raw in tables[name]:
            if (
                time.monotonic() - started > 10
                or not isinstance(raw, dict)
                or set(raw) != set(table.c.keys())
            ):
                raise ValueError("Invalid archive row")
            row = {}
            for column in table.columns:
                value = raw[column.name]
                if value is None:
                    if not column.nullable:
                        raise ValueError("Invalid archive null")
                elif isinstance(column.type, LargeBinary):
                    if not isinstance(value, dict) or set(value) != {"$bytes"}:
                        raise ValueError("Invalid archive file")
                    value = base64.b64decode(value["$bytes"], validate=True)
                    if len(value) > 8 * 1024 * 1024:
                        raise ValueError("Archive file too large")
                elif isinstance(column.type, Boolean):
                    if type(value) is not bool:
                        raise ValueError("Invalid archive boolean")
                elif isinstance(column.type, Integer):
                    if type(value) is not int or abs(value) > 2**63 - 1:
                        raise ValueError("Invalid archive integer")
                elif isinstance(column.type, Float):
                    if type(value) not in (float, int) or not math.isfinite(value):
                        raise ValueError("Invalid archive number")
                elif (
                    not isinstance(value, str)
                    or len(value.encode()) > MAX_BYTES
                    or getattr(column.type, "length", None)
                    and len(value) > column.type.length
                ):
                    raise ValueError("Invalid archive text")
                row[column.name] = value
            if "account_id" in row and row["account_id"] != account_id:
                raise ValueError("Archive owner mismatch")
            key = tuple(row[col.name] for col in table.primary_key)
            if key in keys:
                raise ValueError("Duplicate archive identity")
            keys.add(key)
            if name in schemas:
                schemas[name].model_validate(row)
            if (
                "created_at" in row
                and datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).utcoffset()
                is None
            ):
                raise ValueError("Archive UTC offset required")
            if name == "account_preferences":
                if row["kind"] not in SPECS or row["revision"] < 0:
                    raise ValueError("Invalid archive preference")
                schema, _ = SPECS[row["kind"]]
                schema.model_validate(
                    {**json.loads(row["payload"]), "revision": row["revision"]}
                    if row["kind"] == "planning"
                    else json.loads(row["payload"])
                )
            rows.append(row)
        prepared[name], identities[name] = rows, keys
    # Every domain FK must resolve inside this archive, never to another account's live row.
    indices = {
        name: {
            col.name: {row[col.name] for row in rows}
            for col in Base.metadata.tables[name].columns
            if col.primary_key or any(fk.column.name == col.name for fk in col.foreign_keys)
        }
        for name, rows in prepared.items()
    }
    for name, rows in prepared.items():
        for row in rows:
            for column in Base.metadata.tables[name].columns:
                for fk in column.foreign_keys:
                    value, target = row[column.name], fk.column.table.name
                    if value is None:
                        continue
                    if target == "accounts":
                        valid = value == account_id
                    else:
                        valid = target in indices and value in indices[target].get(
                            fk.column.name, set()
                        )
                    if not valid:
                        raise ValueError("Archive parent mismatch")
    terms = {row["id"]: row for row in prepared["terms"]}
    courses = {row["id"]: row for row in prepared["courses"]}
    weights = {}
    for row in prepared["grades"]:
        weights[row["course_id"]] = weights.get(row["course_id"], 0) + (row["weight"] or 0)
    if any(value > 100.000001 for value in weights.values()):
        raise ValueError("Archive grade weights exceed 100%")
    for row in prepared["timetable"]:
        slot_occurrences(
            SimpleNamespace(**row), SimpleNamespace(**terms[courses[row["course_id"]]["term_id"]])
        )
    return prepared


class AccountRestore(AccountArchive):
    def preview(self, account_id, token, backup_id, password):
        with Session(self.engine) as db:
            require_account_session(db, account_id, token)
        data = self.read(account_id, backup_id, password)
        validate_tables(account_id, data["tables"])
        id = str(uuid4())
        with Session(self.engine) as db:
            begin_academic_write(db)
            require_account_session(db, account_id, token)
            current = self.collect(db, account_id)
            row = db.get(AccountPreference, (account_id, "restore_preview"))
            if row is None:
                row = AccountPreference(account_id=account_id, kind="restore_preview", revision=0)
                db.add(row)
            row.payload = json.dumps(
                {
                    "id": id,
                    "backup_id": backup_id,
                    "source_digest": digest(data["tables"]),
                    "current_digest": digest(current),
                    "session_hash": token_hash(token),
                    "expires": int(time.time()) + 600,
                }
            )
            row.revision += 1
            db.commit()
        return {
            "id": id,
            "counts": {name: len(rows) for name, rows in data["tables"].items()},
            "reconnect_required": True,
            "relogin_required": True,
        }

    def confirm(self, account_id, token, id, password):
        with Session(self.engine) as db:
            require_account_session(db, account_id, token)
            row = db.get(AccountPreference, (account_id, "restore_preview"))
            stored = json.loads(row.payload) if row else {}
            if (
                stored.get("id") != id
                or stored.get("session_hash") != token_hash(token)
                or stored.get("expires", 0) <= time.time()
            ):
                raise ValueError("Restore preview expired")
        data = self.read(account_id, stored["backup_id"], password)
        if digest(data["tables"]) != stored["source_digest"]:
            raise ValueError("Archive changed")
        prepared = validate_tables(account_id, data["tables"])
        safety = self.create(account_id, password)
        with Session(self.engine) as db:
            begin_academic_write(db)
            require_account_session(db, account_id, token)
            row = db.get(AccountPreference, (account_id, "restore_preview"))
            if (
                not row
                or json.loads(row.payload) != stored
                or stored["expires"] <= time.time()
                or digest(self.collect(db, account_id)) != stored["current_digest"]
            ):
                raise ValueError("Account changed; make a new restore preview")
            queries = owned_queries(account_id)
            for name in reversed(ORDER):
                table = Base.metadata.tables[name]
                keys = list(table.primary_key.columns)
                owned = queries[name].with_only_columns(*keys)
                db.execute(delete(table).where(tuple_(*keys).in_(owned)))
            for name in ORDER:
                table = Base.metadata.tables[name]
                if name == "task_status_history":
                    # Task insertion triggers create new marks; restore the recorded history instead.
                    db.execute(
                        delete(table).where(
                            table.c.task_id.in_(
                                select(Base.metadata.tables["tasks"].c.id).where(
                                    Base.metadata.tables["tasks"].c.account_id == account_id
                                )
                            )
                        )
                    )
                if prepared[name]:
                    db.execute(insert(table), prepared[name])
            for name in (
                "account_provider_records",
                "account_oauth_states",
                "account_mail_reviews",
            ):
                table = Base.metadata.tables[name]
                db.execute(delete(table).where(table.c.account_id == account_id))
            for connection in db.scalars(
                select(AccountProvider).where(AccountProvider.account_id == account_id)
            ):
                connection.credentials, connection.authorized = None, False
                connection.revision += 1
                connection.checkpoint, connection.lease_owner, connection.lease_until = (
                    None,
                    None,
                    0,
                )
                connection.last_success, connection.error = None, None
            from .web_push_models import AccountPushConfig, AccountPushDevice

            db.execute(delete(AccountPushDevice).where(AccountPushDevice.account_id == account_id))
            db.execute(delete(AccountPushConfig).where(AccountPushConfig.id == account_id))
            db.execute(delete(LoginSession).where(LoginSession.account_id == account_id))
            db.execute(
                delete(AccountPreference).where(
                    AccountPreference.account_id == account_id,
                    AccountPreference.kind == "backup_schedule",
                )
            )
            db.delete(row)
            db.commit()
        return {
            "restored": True,
            "safety_backup_id": safety["id"],
            "reconnect_required": True,
            "relogin_required": True,
        }
