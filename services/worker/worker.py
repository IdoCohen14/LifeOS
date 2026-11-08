"""Cached provider sync and independent opt-in operational briefing jobs."""

import logging
import sys
import time
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/api"))
from lifeos import academic_models  # noqa: E402,F401
from lifeos.account_operations import AccountOperations, account_runtime  # noqa: E402
from lifeos.account_worker import AccountSyncWorker  # noqa: E402
from lifeos.briefings import BriefingService  # noqa: E402
from lifeos.conversation_history import ConversationHistoryService  # noqa: E402
from lifeos.data_lock import runtime_lock  # noqa: E402
from lifeos.db import data_directory, open_database  # noqa: E402
from lifeos.gmail import GmailService  # noqa: E402
from lifeos.gmail_models import GmailConnection  # noqa: E402
from lifeos.google_calendar import GoogleCalendarService, GoogleProblem  # noqa: E402
from lifeos.google_models import GoogleConnection  # noqa: E402
from lifeos.moodle import MoodleService  # noqa: E402
from lifeos.moodle_models import MoodleConnection  # noqa: E402
from lifeos.scheduled_backups import ScheduledBackupService  # noqa: E402
from lifeos.web_push_delivery import PushDeliveryService  # noqa: E402


def sync_due():
    with runtime_lock(data_directory()):
        return _sync_due()


def _sync_due():
    directory = data_directory()
    engine = open_database(directory)
    try:
        if account_runtime(engine):
            return AccountSyncWorker(engine, directory).tick()
        for model, factory in [
            (GoogleConnection, GoogleCalendarService),
            (GmailConnection, GmailService),
            (MoodleConnection, MoodleService),
        ]:
            with Session(engine) as db:
                row = db.get(model, 1)
                due = bool(
                    row
                    and (
                        row.state in ("connected", "error")
                        or (model is MoodleConnection and row.state == "configured")
                    )
                    and row.next_sync <= int(time.time())
                    and row.lease_until <= int(time.time())
                )
            if due:
                service = factory(engine, directory)
                try:
                    service.sync()
                except GoogleProblem:
                    pass
                finally:
                    service.http.close()
    finally:
        engine.dispose()


def generate_briefings():
    directory = data_directory()
    with runtime_lock(directory):
        engine = open_database(directory)
        try:
            if account_runtime(engine):
                AccountOperations(engine, directory).run("briefings")
            else:
                BriefingService(engine).generate_due()
        except Exception:
            logging.getLogger(__name__).warning(
                "Operational briefing check unavailable; retrying later"
            )
        finally:
            engine.dispose()


def prune_conversation_history():
    directory = data_directory()
    with runtime_lock(directory):
        engine = open_database(directory)
        try:
            if account_runtime(engine):
                AccountOperations(engine, directory).run("history")
            else:
                ConversationHistoryService(engine).prune()
        except Exception:
            logging.getLogger(__name__).warning(
                "Conversation retention check unavailable; retrying later"
            )
        finally:
            engine.dispose()


def scheduled_backup():
    directory = data_directory()
    with runtime_lock(directory):
        engine = open_database(directory)
        try:
            if account_runtime(engine):
                AccountOperations(engine, directory).run("backup")
            else:
                ScheduledBackupService(engine, directory).run_due()
        except Exception:
            logging.getLogger(__name__).warning(
                "Scheduled backup check unavailable; retrying later"
            )
        finally:
            engine.dispose()


def deliver_push():
    directory = data_directory()
    with runtime_lock(directory):
        engine = open_database(directory)
        try:
            if account_runtime(engine):
                AccountOperations(engine, directory).run("push")
            else:
                PushDeliveryService(engine, directory).run_due()
        except Exception:
            logging.getLogger(__name__).warning("Push check unavailable; retrying later")
        finally:
            engine.dispose()


def main():
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        deliver_push,
        "interval",
        seconds=60,
        id="web-push",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        scheduled_backup,
        "interval",
        seconds=60,
        id="encrypted-backup",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        prune_conversation_history,
        "interval",
        minutes=15,
        id="conversation-history-retention",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        sync_due,
        "interval",
        seconds=60,
        id="google-calendar",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        generate_briefings,
        "interval",
        seconds=60,
        id="operational-briefings",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    with runtime_lock(data_directory()):
        scheduler.start()


if __name__ == "__main__":
    main()
