"""Create a consistent local SQLite backup without reading or printing personal records."""

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))


def main():
    from lifeos.db import data_directory

    directory = data_directory()
    source = directory / "lifeos.sqlite3"
    if not source.exists():
        raise SystemExit("No existing LifeOS database found; nothing was changed")
    backups = directory / "backups"
    backups.mkdir(exist_ok=True)
    target = backups / f"lifeos-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.sqlite3"
    with sqlite3.connect(source) as original, sqlite3.connect(target) as backup:
        original.backup(backup)
        if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup integrity verification failed")
    print(f"Verified database backup: {target}")


if __name__ == "__main__":
    main()
