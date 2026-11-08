"""Import a private Moodle subscription locally, without displaying its token."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))


def main():
    from lifeos import academic_models  # noqa: F401 -- register Task relationship
    from lifeos.db import data_directory, migrate, open_database
    from lifeos.google_calendar import GoogleProblem
    from lifeos.moodle import MoodleService, validate_url

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--sync", action="store_true")
    args = parser.parse_args()
    try:
        if args.file.stat().st_size > 32768:
            raise ValueError()
        url = args.file.read_text(encoding="utf-8-sig").strip()
        validate_url(url)
    except Exception:
        raise SystemExit("Missing/invalid Moodle subscription file. No changes made.") from None
    directory = data_directory()
    engine = open_database(directory)
    migrate(engine)
    service = MoodleService(engine, directory)
    try:
        service.configure_feed(url)
        if args.sync:
            service.sync()
        status = service.status()
        print("Moodle subscription stored encrypted; connected:", status["connected"])
        if status["connected"]:
            print("Imported calendar events:", len(service.events()))
    except GoogleProblem as error:
        raise SystemExit("Moodle sync status: " + error.code) from None
    finally:
        service.http.close()
        engine.dispose()


if __name__ == "__main__":
    main()
