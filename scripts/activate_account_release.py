"""Explicit approved offline release; does not reset passwords, generate keys or delete accounts."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    import re

    if (
        not args.confirm
        or not args.data_dir.is_absolute()
        or not re.fullmatch(r"\.next-[a-z0-9-]+", args.build_dir)
    ):
        parser.error("Explicit source, build and --confirm required")
    if not (ROOT / "apps/web" / args.build_dir / "BUILD_ID").is_file():
        parser.error("Prepared production build required")
    from lifeos.local_release import activate_account_release

    print(json.dumps(activate_account_release(args.data_dir, args.account_id, args.build_dir)))


if __name__ == "__main__":
    main()
