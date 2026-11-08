"""Explicit owner lifecycle. Recovery secrets are returned once and stored only as hashes."""

import hmac
import secrets
import time
from collections import deque
from contextlib import contextmanager
from threading import Lock

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .account_deletion import AccountDeletion
from .accounts import matches, normalize_login, password_digest, require_account_session
from .deployment import DeploymentConfig
from .models import Account, AccountLifecycle, LoginSession
from .security import token_hash


class AccountLifecycleService(AccountDeletion):
    def __init__(self, auth, directory):
        self.auth, self.engine, self.directory = auth, auth.engine, directory
        self.attempts, self.lock = deque(), Lock()

    @contextmanager
    def password_slot(self, *, public=False):
        self.auth.require_enabled()
        if public:
            with self.lock:
                now = time.monotonic()
                while self.attempts and self.attempts[0] <= now - 60:
                    self.attempts.popleft()
                if len(self.attempts) >= 10:
                    raise RuntimeError("Recovery busy")
                self.attempts.append(now)
        if not self.auth.slots.acquire(blocking=False):
            raise RuntimeError("Authentication busy")
        try:
            yield
        finally:
            self.auth.slots.release()

    def status(self, account_id, token):
        with Session(self.engine) as db:
            require_account_session(db, account_id, token)
            row = db.get(AccountLifecycle, account_id)
            return {"recovery_configured": bool(row and row.recovery_digest)}

    def generate_key(self, account_id, token, password):
        with self.password_slot(), Session(self.engine) as db:
            begin_academic_write(db)
            require_account_session(db, account_id, token)
            account = db.get(Account, account_id)
            if not matches(password, account.password_digest):
                raise PermissionError("Invalid credentials")
            key = "LFR1-" + secrets.token_urlsafe(32)
            row = db.get(AccountLifecycle, account_id)
            if row is None:
                row = AccountLifecycle(account_id=account_id)
                db.add(row)
            row.recovery_digest = token_hash(key)
            db.commit()
            return {"recovery_key": key}

    def recover(self, login, key, new_password):
        with self.password_slot(public=True), Session(self.engine) as db:
            begin_academic_write(db)
            try:
                login = normalize_login(login)
            except ValueError:
                login = ""
            account = db.scalar(select(Account).where(Account.login == login))
            row = db.get(AccountLifecycle, account.id) if account else None
            expected = row.recovery_digest if row and row.recovery_digest else "0" * 64
            valid = hmac.compare_digest(token_hash(key.strip()), expected)
            if (
                not valid
                or account is None
                or not DeploymentConfig.from_env().allows_account(account.id)
                or not account.enabled
                or row is None
                or not row.recovery_digest
            ):
                return False
            account.password_digest = password_digest(new_password)
            row.recovery_digest = None
            row.deletion_preview = None
            db.execute(delete(LoginSession).where(LoginSession.account_id == account.id))
            db.commit()
            return True
