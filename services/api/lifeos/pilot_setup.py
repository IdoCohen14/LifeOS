"""Offline, empty-server-only pilot provisioning. No personal account import."""

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import academic_models  # noqa: F401
from .accounts import normalize_login, password_digest
from .data_lock import data_lock
from .db import open_database
from .deployment import DeploymentConfig
from .models import Account


def provision_owner(login, password):
    config = DeploymentConfig.from_env()
    if not config.server or not config.pilot_owner_id:
        raise ValueError("Explicit pilot server configuration required")
    directory = Path(os.environ["LIFEOS_DATA_DIR"]).resolve()
    if (
        not (directory / "lifeos.sqlite3").is_file()
        or (directory / ".restore-in-progress").exists()
    ):
        raise ValueError("Initialized, available server database required")
    login, digest = normalize_login(login), password_digest(password)
    with data_lock(directory):
        engine = open_database(directory)
        marker = directory / ".pilot-owner-provisioned"
        try:
            with Session(engine) as db:
                db.execute(text("BEGIN IMMEDIATE"))
                if db.scalar(text("select version_num from alembic_version")) != "0044":
                    raise ValueError("Expected migrated server schema")
                if marker.exists() or db.scalar(select(func.count()).select_from(Account)):
                    raise ValueError("Pilot provisioning requires an unused empty installation")
                # Write intent before commit; interrupted provisioning fails closed instead
                # of permitting silent account recreation after deletion.
                descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as stream:
                    stream.write(config.pilot_owner_id)
                    stream.flush()
                    os.fsync(stream.fileno())
                db.add(
                    Account(
                        id=config.pilot_owner_id,
                        login=login,
                        password_digest=digest,
                        created_at=datetime.now(timezone.utc).isoformat(),
                        enabled=True,
                    )
                )
                db.commit()
        finally:
            engine.dispose()
    return {"owner_created": True}
