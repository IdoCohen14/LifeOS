"""Explicit offline account release: encrypted safety backup, staged migration, saved build."""

import base64
import hashlib
import json
import re
import secrets
import sqlite3
from contextlib import closing
from pathlib import Path

from sqlalchemy import create_engine

from .account_transition import saved_account_mode
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


def preserved_rows(path):
    # Compare sensitive values in memory only; never return or print them to a caller.
    result = {}
    with closing(sqlite3.connect(path)) as db:
        names = [
            row[0]
            for row in db.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%' and name!='alembic_version'"
            )
        ]
        for name in names:
            if not re.fullmatch(r"[a-z_0-9]+", name):
                raise ValueError("Unexpected schema name")
            columns = len(db.execute(f'PRAGMA table_info("{name}")').fetchall())
            order = ",".join(str(index + 1) for index in range(columns))
            rows = db.execute(f'SELECT * FROM "{name}" ORDER BY {order}').fetchall()
            digest = hashlib.sha256()
            for row in rows:
                for value in row:
                    raw = value if isinstance(value, bytes) else repr(value).encode()
                    digest.update(len(raw).to_bytes(8, "big"))
                    digest.update(raw)
            result[name] = (len(rows), digest.hexdigest())
    return result


def activate_account_release(directory, account_id, build_dir):
    directory = Path(directory).resolve()
    if not re.fullmatch(r"\.next-[a-z0-9-]+", build_dir) or not saved_account_mode(directory):
        raise ValueError("Explicit valid account build required")
    with data_lock(directory):
        mode_path = directory / "account-mode.json"
        mode = json.loads(mode_path.read_bytes())
        if mode["account_id"] != account_id or (directory / ".restore-in-progress").exists():
            raise ValueError("Account source mismatch or interrupted recovery")
        source = directory / "lifeos.sqlite3"
        with closing(sqlite3.connect(source)) as db:
            version = db.execute("select version_num from alembic_version").fetchone()[0]
            account = db.execute(
                "select enabled from accounts where id=?", (account_id,)
            ).fetchone()
        if version not in ("0043", "0044") or account != (1,):
            raise ValueError("Unexpected source account/revision")
        before = preserved_rows(source)
        auth_hash = hashlib.sha256((directory / "auth.json").read_bytes()).digest()
        password = secrets.token_urlsafe(48)
        safety = create_backup(directory, password)
        folder = directory / "release-safety"
        folder.mkdir(exist_ok=True)
        if folder.is_symlink() or folder.resolve() != folder:
            raise ValueError("Invalid release safety directory")
        cipher = CredentialVault(folder).encrypt({"password": password})
        receipt = {
            "version": 1,
            "source_schema": version,
            "target_schema": "0044",
            "account_id": account_id,
            "safety_backup_id": safety["id"],
            "previous_mode": mode,
            "password_cipher": base64.b64encode(cipher).decode(),
        }
        atomic_write(folder / (safety["id"] + ".json"), json.dumps(receipt).encode())
        with temporary_database(directory) as staged:
            copy_database(source, staged)
            engine = create_engine("sqlite:///" + str(staged))
            try:
                migrate(engine)
            finally:
                engine.dispose()
            validate_database(staged, directory, "0044")
            after = preserved_rows(staged)
            if any(after.get(name) != value for name, value in before.items()):
                raise ValueError("Existing installation rows changed")
            marker = directory / ".restore-in-progress"
            atomic_write(
                marker,
                json.dumps(
                    {"safety_backup_id": safety["id"], "operation": "account_release"}
                ).encode(),
            )
            copy_database(staged, source)
            if hashlib.sha256((directory / "auth.json").read_bytes()).digest() != auth_hash:
                raise ValueError("Authentication file changed")
            mode["web_build_dir"] = build_dir
            atomic_write(mode_path, json.dumps(mode).encode())
            marker.unlink()
    return {
        "source_schema": version,
        "schema": "0044",
        "safety_backup_id": safety["id"],
        "existing_rows_preserved": True,
        "build_dir": build_dir,
        "account_id": account_id,
    }
