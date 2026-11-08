"""Offline retry for an already confirmed, disabled account deletion. Stop LifeOS first."""

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if (
        not args.confirm
        or not args.data_dir.is_absolute()
        or str(UUID(args.account_id)) != args.account_id
    ):
        parser.error(
            "Explicit absolute data path, canonical account UUID and --confirm are required"
        )
    directory = args.data_dir.resolve()
    if not (directory / "lifeos.sqlite3").is_file():
        parser.error("Existing server database required")
    from lifeos.account_lifecycle import AccountLifecycleService
    from lifeos.accounts import AccountService
    from lifeos.data_lock import data_lock
    from lifeos.db import open_database

    with data_lock(directory):
        engine = open_database(directory)
        try:
            result = AccountLifecycleService(
                AccountService(engine, enabled=True), directory
            ).finish_deletion(args.account_id)
            print(json.dumps(result))
            return 0 if result["deleted"] else 1
        finally:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
