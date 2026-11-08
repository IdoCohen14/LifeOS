"""Operator-only import of Web OAuth configuration into encrypted local storage."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))


def main():
    from lifeos import academic_models  # noqa: F401 -- register Task relationships
    from lifeos.db import data_directory, migrate, open_database
    from lifeos.google_calendar import GoogleCalendarService
    from lifeos.google_routes import GoogleConfig

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        if args.file.stat().st_size > 65536:
            raise ValueError()
        config = json.loads(args.file.read_text(encoding="utf-8"))["web"]
        validated = GoogleConfig(
            client_id=config["client_id"], client_secret=config["client_secret"]
        )
        callback = "http://127.0.0.1:3000/api/integrations/google/callback"
        if callback not in config.get("redirect_uris", []):
            raise ValueError()
    except Exception:
        raise SystemExit(
            "Invalid Web OAuth file or missing local callback; no changes made"
        ) from None
    directory = data_directory()
    engine = open_database(directory)
    migrate(engine)
    service = GoogleCalendarService(engine, directory)
    try:
        service.configure(validated.client_id, validated.client_secret)
        assert service.status()["configured"]
        print("Web OAuth configuration stored encrypted. Account consent is still required.")
    finally:
        service.http.close()
        engine.dispose()


if __name__ == "__main__":
    main()
