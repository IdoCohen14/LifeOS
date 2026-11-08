"""Inspect or restore an encrypted LifeOS backup; restore only while LifeOS is closed."""

import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))


def main():
    from lifeos.db import data_directory
    from lifeos.recovery import RecoveryError, create_backup, inspect_backup, restore_backup

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "inspect", "restore"])
    parser.add_argument("file", nargs="?", type=Path)
    parser.add_argument(
        "--data-dir", type=Path, help="Explicit private data folder used by the LifeOS launcher"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Explicitly authorize replacing local data/password with the backup",
    )
    args = parser.parse_args()
    if args.action in ("inspect", "restore") and not args.file:
        parser.error("Choose a backup file")
    if args.action == "restore" and not args.confirm:
        raise SystemExit(
            "Restore replaces your local data and login hash. Close LifeOS, inspect the backup, then add --confirm only when ready."
        )
    password = getpass.getpass("Backup password (hidden): ")
    if args.action == "backup" and password != getpass.getpass("Confirm backup password: "):
        raise SystemExit("Passwords do not match; nothing changed")
    try:
        directory = args.data_dir.resolve() if args.data_dir else data_directory()
        if args.action == "backup":
            result = create_backup(directory, password)
        elif args.action == "inspect":
            result = inspect_backup(args.file, password)
        else:
            result = restore_backup(args.file, password, directory)
        print(json.dumps(result, indent=2))
    except RecoveryError as error:
        raise SystemExit(str(error)) from None
    except Exception:
        raise SystemExit(
            "Recovery failed. Existing data/safety backup was preserved; check permissions and the selected file."
        ) from None


if __name__ == "__main__":
    main()
