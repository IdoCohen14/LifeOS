"""Independent opt-in account background jobs; no legacy singleton data paths."""

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .account_backup_schedule import AccountBackupSchedule
from .account_briefings import AccountBriefings
from .account_conversation import AccountConversation
from .deployment import DeploymentConfig
from .models import Account, AccountConversationTurn, AccountPreference
from .web_push_delivery import PushDeliveryService
from .web_push_models import AccountPushDevice


def account_runtime(engine):
    if DeploymentConfig.from_env().server or os.environ.get("LIFEOS_ACCOUNT_MODE") == "1":
        return True
    with Session(engine) as db:
        if db.scalar(select(Account.id).limit(1)) is not None:
            raise RuntimeError("Account data requires account mode")
    return False


class AccountOperations:
    def __init__(self, engine, directory):
        self.engine, self.directory = engine, directory

    def owners(self, kind):
        query = select(Account.id)
        pilot = DeploymentConfig.from_env().pilot_owner_id
        if pilot:
            query = query.where(Account.id == pilot, Account.enabled.is_(True))
        if kind in ("briefings", "backup"):
            query = query.join(AccountPreference).where(
                AccountPreference.kind
                == ("briefings" if kind == "briefings" else "backup_schedule")
            )
        elif kind == "push":
            query = query.join(AccountPushDevice).where(AccountPushDevice.enabled.is_(True))
        elif kind == "history":
            query = query.join(AccountConversationTurn)
        else:
            raise ValueError("Invalid account job")
        if kind != "history":
            query = query.where(Account.enabled.is_(True))
        with Session(self.engine) as db:
            return list(db.scalars(query.distinct().order_by(Account.id)))

    def prune_history(self, owner):
        with Session(self.engine) as db:
            begin_academic_write(db)
            AccountConversation(self.engine).prune(db, owner)
            db.commit()

    def run(self, kind, *, handler=None):
        if handler is None:
            handler = {
                "briefings": lambda owner: AccountBriefings(self.engine).generate_due(owner),
                "backup": lambda owner: AccountBackupSchedule(self.engine, self.directory).run_due(
                    owner
                ),
                "push": lambda owner: PushDeliveryService(
                    self.engine, self.directory, account_id=owner
                ).run_due(),
                "history": self.prune_history,
            }[kind]
        completed = failed = 0
        for owner in self.owners(kind):
            try:
                handler(owner)
                completed += 1
            except Exception:
                failed += 1
        return {"completed": completed, "failed": failed}
