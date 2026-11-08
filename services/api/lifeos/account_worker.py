"""Account provider scheduling core; called only by explicit account-mode runtime."""

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .account_braude import AccountBraude
from .account_calendar import AccountCalendar
from .account_gmail import AccountGmail
from .account_moodle import AccountMoodle
from .account_providers import AccountProviders
from .deployment import DeploymentConfig
from .models import Account, AccountProvider


class AccountSyncWorker:
    def __init__(self, engine, directory, *, adapters=None):
        self.engine = engine
        self.storage = AccountProviders(engine, directory)
        self.adapters = adapters or {
            "google": AccountCalendar(engine, directory),
            "gmail": AccountGmail(engine, directory),
            "moodle": AccountMoodle(engine, directory),
            "braude": AccountBraude(engine, directory),
        }

    def due(self):
        now = int(time.time())
        jobs = []
        with Session(self.engine) as db:
            pilot = DeploymentConfig.from_env().pilot_owner_id
            rows = db.scalars(
                select(AccountProvider)
                .join(Account, Account.id == AccountProvider.account_id)
                .where(
                    Account.enabled.is_(True),
                    Account.id == pilot if pilot else Account.enabled.is_(True),
                    AccountProvider.credentials.is_not(None),
                    AccountProvider.authorized.is_(True),
                    AccountProvider.next_sync <= now,
                    AccountProvider.lease_until <= now,
                )
                .order_by(
                    AccountProvider.next_sync, AccountProvider.account_id, AccountProvider.provider
                )
                .limit(100)
            )
            for row in rows:
                try:
                    payload = self.storage.vault.decrypt(row.credentials)
                    if (
                        payload.get("account_id") != row.account_id
                        or payload.get("provider") != row.provider
                    ):
                        continue
                    values = payload["values"]
                    ready = bool(
                        values.get("url")
                        if row.provider in {"moodle", "braude"}
                        else values.get("refresh_token")
                    )
                    if ready:
                        jobs.append((row.account_id, row.provider))
                except Exception:
                    continue
        return jobs

    def tick(self):
        completed = failed = 0
        for account_id, provider in self.due():
            try:
                self.adapters[provider].sync(account_id)
                completed += 1
            except Exception:
                failed += 1
        return {"completed": completed, "failed": failed}
