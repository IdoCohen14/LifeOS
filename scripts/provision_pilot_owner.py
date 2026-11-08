"""Provision one owner offline using the private server environment, never password argv."""

import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login", required=True)
    parser.add_argument(
        "--password-stdin", action="store_true", help="Read one password line without echoing it"
    )
    args = parser.parse_args()
    password = (
        sys.stdin.readline(1026).rstrip("\r\n")
        if args.password_stdin
        else getpass.getpass("Pilot password (8+ characters): ")
    )
    from lifeos.pilot_setup import provision_owner

    try:
        print(json.dumps(provision_owner(args.login, password)))
    except Exception:
        print(
            "Pilot owner was not provisioned. Check private configuration, empty database and offline locks.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
