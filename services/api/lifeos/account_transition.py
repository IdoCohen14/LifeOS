"""Offline legacy-to-account transition preparation. Preview never upgrades the source."""

import base64
import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from .accounts import normalize_login
from .recovery import MAX_DATABASE, validate_auth

SOURCE_TABLES = (
    "tasks",
    "events",
    "terms",
    "courses",
    "academic_items",
    "timetable",
    "grades",
    "documents",
    "document_sections",
    "event_series",
    "series_occurrences",
    "task_time_blocks",
    "task_status_history",
    "task_history_metadata",
    "settings",
    "planning_preferences",
    "notification_preferences",
    "notification_reads",
    "notification_actions",
    "recommendation_dismissals",
    "briefing_schedule",
    "scheduled_briefings",
    "assistant_history_preferences",
    "assistant_conversation_turns",
    "moodle_changes",
    "google_connection",
    "google_calendars",
    "google_records",
    "gmail_connection",
    "gmail_messages",
    "gmail_reviewed",
    "moodle_connection",
    "moodle_events",
    "push_config",
    "push_devices",
    "push_deliveries",
    "backup_schedule",
    "automatic_backup_files",
)


def readonly_database(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    db.execute("BEGIN")
    return db


def saved_account_mode(directory):
    path = Path(directory).resolve() / "account-mode.json"
    if not path.exists():
        return False
    if path.is_symlink() or path.stat().st_size > 4096:
        raise ValueError("Invalid saved account mode")
    data = json.loads(path.read_bytes())
    if data.get("version") != 1 or data.get("enabled") is not True:
        raise ValueError("Invalid saved account mode")
    UUID(data["account_id"])
    return True


def saved_account_build(directory):
    if not saved_account_mode(directory):
        raise ValueError("Saved account mode required")
    data = json.loads((Path(directory).resolve() / "account-mode.json").read_bytes())
    build = data.get("web_build_dir", ".next-account-release")
    if not isinstance(build, str) or not re.fullmatch(r"\.next(?:-[a-z0-9-]+)?", build):
        raise ValueError("Invalid saved web build")
    return build


def preview_transition(directory, login, *, target_id=None):
    directory = Path(directory).resolve()
    database = directory / "lifeos.sqlite3"
    if not database.is_file() or not (directory / "auth.json").is_file():
        raise FileNotFoundError("Existing legacy installation required")
    if (directory / "account-mode.json").exists() or (directory / ".restore-in-progress").exists():
        raise ValueError("Source already transitioned or requires recovery")
    if database.stat().st_size > MAX_DATABASE:
        raise ValueError("Transition database resource limit")
    login = normalize_login(login)
    target_id = str(uuid4()) if target_id is None else str(UUID(target_id))
    auth = (directory / "auth.json").read_bytes()
    validate_auth(auth)
    digest, counts = hashlib.sha256(auth), {}
    key = directory / "provider.key"
    if key.exists():
        if key.stat().st_size > 4096:
            raise ValueError("Invalid provider key")
        digest.update(key.read_bytes())
    started, total = time.monotonic(), 0
    with closing(readonly_database(database)) as db:
        db.set_progress_handler(lambda: int(time.monotonic() - started > 20), 10000)
        version = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        if version not in ("0028", "0043", "0044"):
            raise ValueError("Unsupported transition source revision")
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "accounts" in names and db.execute("SELECT count(*) FROM accounts").fetchone()[0]:
            raise ValueError("Source already contains accounts")
        digest.update(version.encode())
        for table in SOURCE_TABLES:
            if table not in names:
                continue
            digest.update(table.encode())
            count = 0
            for row in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
                total += 1
                count += 1
                if total > 100000 or time.monotonic() - started > 20:
                    raise ValueError("Transition resource limit")
                for value in row:
                    encoded = (
                        value
                        if isinstance(value, bytes)
                        else json.dumps(value, ensure_ascii=False).encode()
                    )
                    digest.update(("bytes" if isinstance(value, bytes) else "json").encode())
                    digest.update(len(encoded).to_bytes(8, "big"))
                    digest.update(encoded)
            counts[table] = count
        providers = {
            provider: bool(
                db.execute(
                    f'SELECT credentials IS NOT NULL FROM "{provider}_connection" WHERE id=1'
                ).fetchone()[0]
            )
            if f"{provider}_connection" in names
            and db.execute(f'SELECT 1 FROM "{provider}_connection" WHERE id=1').fetchone()
            else False
            for provider in ("google", "gmail", "moodle")
        }
    policy = {
        "source": str(directory),
        "source_digest": digest.hexdigest(),
        "target_id": target_id,
        "target_login": login,
        "version": 1,
    }
    approval = hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()
    return {
        **policy,
        "source_schema": version,
        "counts": counts,
        "providers_configured": providers,
        "approval_digest": approval,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reuse_existing_password": True,
        "requires_offline_apply": True,
        "requires_explicit_source_target_approval": True,
    }


def apply_transition(directory, plan, *, approval_digest, before_install=None):
    """Operator-only offline action. Caller must obtain explicit source/target approval."""
    from .account_transition_copy import transform
    from .credential_vault import CredentialVault
    from .data_lock import data_lock
    from .db import migrate
    from .recovery import (
        atomic_write,
        copy_database,
        create_backup,
        temporary_database,
        validate_database,
    )

    directory = Path(directory).resolve()
    if not secrets.compare_digest(str(approval_digest), str(plan.get("approval_digest", ""))):
        raise PermissionError("Explicit matching transition approval required")
    if str(directory) != plan.get("source"):
        raise PermissionError("Transition source mismatch")
    with data_lock(directory):
        fresh = preview_transition(directory, plan["target_login"], target_id=plan["target_id"])
        if not secrets.compare_digest(fresh["approval_digest"], plan["approval_digest"]):
            raise ValueError("Source changed; review a new transition plan")
        plan = fresh
        # Reuse the existing full encrypted installation backup format for offline recovery.
        password = secrets.token_urlsafe(48)
        safety = create_backup(directory, password)
        folder = directory / "transition-safety"
        folder.mkdir(exist_ok=True)
        if folder.resolve() != folder or folder.is_symlink():
            raise ValueError("Invalid transition safety directory")
        cipher = CredentialVault(folder).encrypt({"password": password})
        receipt = {
            "version": 1,
            "source": str(directory),
            "approval_digest": approval_digest,
            "safety_backup_id": safety["id"],
            "account_id": plan["target_id"],
            "password_cipher": base64.b64encode(cipher).decode(),
        }
        receipt_path = folder / (safety["id"] + ".json")
        atomic_write(receipt_path, json.dumps(receipt).encode())
        source = directory / "lifeos.sqlite3"
        marker = directory / ".restore-in-progress"
        mode = directory / "account-mode.json"
        with temporary_database(directory) as original, temporary_database(directory) as staging:
            copy_database(source, original)
            copy_database(original, staging)
            # Alembic runs on the clone only. The live file stays on its old revision until install.
            from sqlalchemy import create_engine

            engine = create_engine("sqlite:///" + str(staging))
            try:
                migrate(engine)
            finally:
                engine.dispose()
            with closing(sqlite3.connect(staging)) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("BEGIN IMMEDIATE")
                transform(
                    db,
                    plan,
                    json.loads((directory / "auth.json").read_bytes()),
                    CredentialVault(directory),
                )
                if db.execute("PRAGMA foreign_key_check").fetchone():
                    raise ValueError("Transition foreign-key validation failed")
                for table in ("tasks", "events", "terms", "event_series"):
                    count = db.execute(
                        f'SELECT count(*) FROM "{table}" WHERE account_id=?', (plan["target_id"],)
                    ).fetchone()[0]
                    if count != plan["counts"].get(table, 0):
                        raise ValueError("Transition record count changed")
                db.commit()
            validate_database(staging, directory, "0044")
            if before_install is not None:
                before_install(
                    staging
                )  # Fixture hook for forced-failure acceptance; never persisted.
            atomic_write(
                marker,
                json.dumps(
                    {"safety_backup_id": safety["id"], "transition_receipt": receipt_path.name}
                ).encode(),
            )
            try:
                copy_database(staging, source)
                atomic_write(
                    mode,
                    json.dumps(
                        {"version": 1, "enabled": True, "account_id": plan["target_id"]}
                    ).encode(),
                )
                marker.unlink()
            except BaseException:
                # Keep the marker if rollback itself fails so the app cannot start on partial data.
                copy_database(original, source)
                mode.unlink(missing_ok=True)
                marker.unlink(missing_ok=True)
                raise
        return {
            "account_id": plan["target_id"],
            "login": plan["target_login"],
            "safety_backup_id": safety["id"],
            "receipt": str(receipt_path),
            "reused_password": True,
            "preserved_active_sessions": True,
        }


def rollback_transition(directory, backup_id, *, approval_digest):
    from .credential_vault import CredentialVault
    from .data_lock import data_lock
    from .recovery import (
        atomic_write,
        copy_database,
        temporary_database,
        unpack_backup,
        validate_database,
    )

    directory = Path(directory).resolve()
    if str(UUID(backup_id)) != backup_id:
        raise ValueError("Invalid transition backup identity")
    folder = directory / "transition-safety"
    receipt_path = folder / (backup_id + ".json")
    if (
        folder.resolve() != folder
        or receipt_path.is_symlink()
        or receipt_path.stat().st_size > 16384
    ):
        raise ValueError("Invalid transition safety receipt")
    receipt = json.loads(receipt_path.read_bytes())
    if (
        receipt.get("source") != str(directory)
        or receipt.get("safety_backup_id") != backup_id
        or not secrets.compare_digest(str(receipt.get("approval_digest")), str(approval_digest))
    ):
        raise PermissionError("Explicit matching rollback approval required")
    secret = CredentialVault(folder).decrypt(
        base64.b64decode(receipt["password_cipher"], validate=True)
    )
    path = directory / "backups" / (backup_id + ".lifeosbackup")
    if path.is_symlink():
        raise ValueError("Invalid transition backup path")
    with data_lock(directory):
        entries, manifest = unpack_backup(path, secret["password"])
        source = directory / "lifeos.sqlite3"
        marker = directory / ".restore-in-progress"
        mode = directory / "account-mode.json"
        previous_mode = mode.read_bytes() if mode.exists() else None
        with temporary_database(directory) as incoming, temporary_database(directory) as current:
            incoming.write_bytes(entries["lifeos.sqlite3"])
            validate_database(incoming, directory, manifest["schema"])
            copy_database(source, current)
            # Preserve a recoverable current copy before explicitly replacing account data.
            saved = folder / (str(uuid4()) + ".rollback-current")
            payload = {"database": base64.b64encode(current.read_bytes()).decode()}
            atomic_write(saved, CredentialVault(folder).encrypt(payload))
            atomic_write(marker, json.dumps({"safety_backup_id": backup_id}).encode())
            try:
                copy_database(incoming, source)
                (directory / "account-mode.json").unlink(missing_ok=True)
                marker.unlink()
            except BaseException:
                copy_database(current, source)
                if previous_mode is not None:
                    atomic_write(mode, previous_mode)
                marker.unlink(missing_ok=True)
                raise
    return {"restored_legacy_schema": manifest["schema"], "preserved_current_copy": saved.name}
