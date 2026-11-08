"""Reviewed owner-only deletion, with disabled retry state and no external mutations."""

import json
import time
from uuid import uuid4

from sqlalchemy import MetaData, and_, delete, func, or_, select, tuple_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .accounts import matches, require_account_session
from .data_lock import account_storage_lock
from .db import Base
from .models import Account, AccountLifecycle, LoginSession
from .security import token_hash


def owned_filters(account_id, metadata=None):
    """Follow declared FK ownership in parent order; direct owner columns are authoritative."""
    predicates = {}
    for table in (Base.metadata if metadata is None else metadata).sorted_tables:
        direct = [
            fk.parent == account_id
            for fk in table.foreign_keys
            if fk.column.table.name == "accounts"
        ]
        if direct:
            predicates[table.name] = or_(*direct)
            continue
        inherited = []
        for constraint in table.foreign_key_constraints:
            elements = list(constraint.elements)
            parent = elements[0].column.table
            if parent.name in predicates:
                inherited.append(
                    tuple_(*(fk.parent for fk in elements)).in_(
                        select(*(fk.column for fk in elements)).where(predicates[parent.name])
                    )
                )
        if inherited:
            predicates[table.name] = and_(*inherited)
    return predicates


class AccountDeletion:
    def deletion_metadata(self):
        # Offline retry does not import the full application/model registry. Inspect the
        # actual migrated schema so an unimported dependent table cannot escape the purge.
        metadata = MetaData()
        metadata.reflect(
            bind=self.engine, only=lambda name, _: not name.startswith("document_search")
        )
        return metadata

    def deletion_preview(self, account_id, token):
        metadata = self.deletion_metadata()
        with Session(self.engine) as db:
            begin_academic_write(db)
            require_account_session(db, account_id, token)
            counts = {
                name: db.scalar(
                    select(func.count()).select_from(metadata.tables[name]).where(predicate)
                )
                for name, predicate in owned_filters(account_id, metadata).items()
                if name != "account_lifecycle"
            }
            preview = {
                "id": str(uuid4()),
                "session_hash": token_hash(token),
                "expires": int(time.time()) + 600,
            }
            row = db.get(AccountLifecycle, account_id)
            if row is None:
                row = AccountLifecycle(account_id=account_id)
                db.add(row)
            row.deletion_preview = json.dumps(preview)
            login = db.get(Account, account_id).login
            db.commit()
        return {
            "id": preview["id"],
            "login": login,
            "counts": counts,
            "expires": preview["expires"],
        }

    def confirm_deletion(self, account_id, token, preview_id, password, login):
        with self.password_slot(), Session(self.engine) as db:
            begin_academic_write(db)
            require_account_session(db, account_id, token)
            account = db.get(Account, account_id)
            if login != account.login or not matches(password, account.password_digest):
                raise PermissionError("Invalid credentials")
            row = db.get(AccountLifecycle, account_id)
            stored = json.loads(row.deletion_preview) if row and row.deletion_preview else {}
            if (
                stored.get("id") != preview_id
                or stored.get("session_hash") != token_hash(token)
                or stored.get("expires", 0) <= time.time()
            ):
                raise ValueError("Deletion review expired; review again")
            account.enabled = False
            row.deletion_state, row.deletion_preview, row.recovery_digest = (
                "cleanup_pending",
                None,
                None,
            )
            db.execute(delete(LoginSession).where(LoginSession.account_id == account_id))
            db.commit()
        return self.finish_deletion(account_id)

    def cleanup_archives(self, account_id):
        from .account_archive import AccountArchive

        folder = AccountArchive(self.engine, self.directory).folder(account_id)
        if not folder.exists():
            return
        # Owner folder is validated above; reject unexpected trees/symlinks instead of following them.
        for path in folder.iterdir():
            if path.is_symlink() or not path.is_file():
                raise ValueError("Unexpected account archive entry")
            path.unlink()
        folder.rmdir()

    def finish_deletion(self, account_id):
        self.auth.require_enabled()
        with Session(self.engine) as db:
            account, row = db.get(Account, account_id), db.get(AccountLifecycle, account_id)
            if not account or account.enabled or not row or row.deletion_state != "cleanup_pending":
                raise ValueError("No confirmed pending account deletion")
        try:
            with account_storage_lock(self.directory, account_id):
                self.cleanup_archives(account_id)
                metadata = self.deletion_metadata()
                with Session(self.engine) as db:
                    begin_academic_write(db)
                    account, row = db.get(Account, account_id), db.get(AccountLifecycle, account_id)
                    if (
                        not account
                        or account.enabled
                        or not row
                        or row.deletion_state != "cleanup_pending"
                    ):
                        raise ValueError("Account deletion state changed")
                    predicates = owned_filters(account_id, metadata)
                    for table in reversed(metadata.sorted_tables):
                        if table.name in predicates:
                            db.execute(delete(table).where(predicates[table.name]))
                    db.execute(
                        delete(Account).where(Account.id == account_id, Account.enabled.is_(False))
                    )
                    db.commit()
        except (OSError, RuntimeError, ValueError, SQLAlchemyError):
            return {"deleted": False, "cleanup_pending": True}
        return {"deleted": True, "cleanup_pending": False}
