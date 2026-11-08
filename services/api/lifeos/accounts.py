"""Internal account authentication foundation. No public routes until tenant isolation."""

import hashlib
import hmac
import json
import secrets
import time
from collections import deque
from datetime import datetime, timezone
from threading import BoundedSemaphore, Lock
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .deployment import DeploymentConfig
from .models import Account, LoginSession
from .security import token_hash


def require_account_session(db, account_id, token):
    if not DeploymentConfig.from_env().allows_account(account_id):
        raise PermissionError("Account unavailable")
    account = db.get(Account, account_id)
    session = db.get(LoginSession, token_hash(token))
    if (
        account is None
        or not account.enabled
        or session is None
        or session.account_id != account_id
        or session.expires <= int(time.time())
    ):
        raise PermissionError("Invalid account session")
    return session


def normalize_login(value):
    value = value.strip().casefold()
    if not value or len(value) > 254 or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError("Invalid login")
    return value


def password_digest(password):
    if not 8 <= len(password) <= 1024:
        raise ValueError("Password must contain 8–1024 characters")
    salt = secrets.token_bytes(32)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return json.dumps({"version": 1, "salt": salt.hex(), "hash": digest.hex()})


def matches(password, stored):
    try:
        value = json.loads(stored)
        if value["version"] != 1 or not 8 <= len(password) <= 1024:
            return False
        salt = bytes.fromhex(value["salt"])
        if len(salt) != 32:
            return False
        digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
        return hmac.compare_digest(digest.hex(), value["hash"])
    except (KeyError, ValueError, TypeError):
        return False


class AccountService:
    def change_password(self, account_id, current_password, new_password):
        self.require_enabled()
        if not self.slots.acquire(blocking=False):
            raise RuntimeError("Authentication busy")
        try:
            with Session(self.engine) as db:
                account = db.get(Account, account_id)
                stored = account.password_digest if account else self.dummy
                valid = matches(current_password, stored)
                if not valid or account is None or not account.enabled:
                    return False
                digest = password_digest(new_password)
                result = db.execute(
                    update(Account)
                    .where(
                        Account.id == account_id,
                        Account.password_digest == stored,
                        Account.enabled.is_(True),
                    )
                    .values(password_digest=digest)
                )
                if result.rowcount != 1:
                    return False
                db.execute(delete(LoginSession).where(LoginSession.account_id == account_id))
                db.commit()
                return True
        finally:
            self.slots.release()

    def logout(self, token):
        self.require_enabled()
        with Session(self.engine) as db:
            db.execute(
                delete(LoginSession).where(
                    LoginSession.token_hash == token_hash(token),
                    LoginSession.account_id.is_not(None),
                )
            )
            db.commit()

    def __init__(self, engine, *, enabled=False):
        self.engine, self.enabled = engine, enabled
        self.slots, self.lock, self.attempts = BoundedSemaphore(2), Lock(), deque()
        self.dummy = password_digest(secrets.token_urlsafe(32))

    def require_enabled(self):
        if not self.enabled:
            raise RuntimeError("Account authentication is not activated")

    def register(self, login, password):
        self.require_enabled()
        if DeploymentConfig.from_env().pilot_owner_id:
            raise PermissionError("Registration is closed")
        login = normalize_login(login)
        if not self.slots.acquire(blocking=False):
            raise RuntimeError("Authentication busy")
        try:
            digest = password_digest(password)
        finally:
            self.slots.release()
        id = str(uuid4())
        try:
            with Session(self.engine) as db:
                db.add(
                    Account(
                        id=id,
                        login=login,
                        password_digest=digest,
                        created_at=datetime.now(timezone.utc).isoformat(),
                        enabled=True,
                    )
                )
                db.commit()
        except IntegrityError:
            raise ValueError("Account could not be created") from None
        return id

    def login(self, login, password):
        self.require_enabled()
        with self.lock:
            now = time.monotonic()
            while self.attempts and self.attempts[0] <= now - 60:
                self.attempts.popleft()
            if len(self.attempts) >= 10:
                raise RuntimeError("Authentication busy")
            self.attempts.append(now)
        if not self.slots.acquire(blocking=False):
            raise RuntimeError("Authentication busy")
        try:
            try:
                normalized = normalize_login(login)
            except ValueError:
                normalized = ""
            with Session(self.engine) as db:
                from .academic import begin_academic_write

                # Serialize credential validation and session creation with recovery/deletion.
                begin_academic_write(db)
                account = db.scalar(select(Account).where(Account.login == normalized))
                allowed = account is not None and DeploymentConfig.from_env().allows_account(account.id)
                valid = matches(password, account.password_digest if allowed else self.dummy)
                if not valid or not allowed or not account.enabled:
                    return None
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                db.add(
                    LoginSession(
                        token_hash=token_hash(token),
                        csrf=csrf,
                        expires=int(time.time()) + 43200,
                        account_id=account.id,
                    )
                )
                db.commit()
                return {"token": token, "csrf": csrf, "account_id": account.id}
        finally:
            self.slots.release()
