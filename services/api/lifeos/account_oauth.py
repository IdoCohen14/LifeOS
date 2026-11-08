"""Account-bound OAuth core; not exposed until complete tenant activation."""

import base64
import hashlib
import os
import secrets
import time
from urllib.parse import urlencode

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .account_providers import AccountProviders
from .deployment import DeploymentConfig
from .google_calendar import SCOPES
from .models import AccountOAuthState, AccountProvider, LoginSession
from .security import token_hash


class AccountOAuth(AccountProviders):
    def prepare_application(self, account_id, provider):
        """Share only server application configuration; never another user's tokens."""
        self.scopes(provider)
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            row = db.get(AccountProvider, (account_id, provider))
            values, revision = {}, row.revision if row else 0
            if row and row.credentials:
                decoded = self.vault.decrypt(row.credentials)
                if decoded.get("account_id") != account_id or decoded.get("provider") != provider:
                    raise PermissionError("Credential owner mismatch")
                values = decoded["values"]
        client_id = os.environ.get("LIFEOS_GOOGLE_CLIENT_ID", "")
        secret = os.environ.get("LIFEOS_GOOGLE_CLIENT_SECRET", "")
        if client_id and secret:
            if values.get("client_id") != client_id or values.get("client_secret") != secret:
                self.configure(
                    account_id,
                    provider,
                    {"client_id": client_id, "client_secret": secret},
                    expected_revision=revision,
                )
        elif not values.get("client_id") or not values.get("client_secret"):
            raise ValueError("OAuth application not configured")

    def scopes(self, provider):
        if provider == "google":
            return SCOPES
        if provider == "gmail":
            return ["https://www.googleapis.com/auth/gmail.readonly"]
        raise ValueError("Unsupported OAuth provider")

    def require_session(self, db, account_id, token):
        self.authorize(db, account_id)
        row = db.get(LoginSession, token_hash(token))
        if row is None or row.account_id != account_id or row.expires <= int(time.time()):
            raise PermissionError("Invalid account session")
        return row

    def start(self, account_id, provider, token, *, web_port=3000):
        scopes = self.scopes(provider)
        if type(web_port) is not int or not 1024 <= web_port <= 65535:
            raise ValueError("Invalid local port")
        redirect = DeploymentConfig.from_env().oauth_callback(web_port)
        with Session(self.engine) as db:
            begin_academic_write(db)
            session = self.require_session(db, account_id, token)
            connection = db.get(AccountProvider, (account_id, provider))
            if connection is None or connection.credentials is None:
                raise ValueError("Provider not configured")
            decoded = self.vault.decrypt(connection.credentials)
            if decoded.get("account_id") != account_id or decoded.get("provider") != provider:
                raise PermissionError("Credential owner mismatch")
            values = decoded["values"]
            if not values.get("client_id") or not values.get("client_secret"):
                raise ValueError("OAuth client not configured")
            state = f"account.{provider}." + secrets.token_urlsafe(32)
            verifier = secrets.token_urlsafe(64)
            db.execute(
                delete(AccountOAuthState).where(AccountOAuthState.expires <= int(time.time()))
            )
            db.execute(
                delete(AccountOAuthState).where(
                    AccountOAuthState.session_hash == session.token_hash,
                    AccountOAuthState.provider == provider,
                )
            )
            db.add(
                AccountOAuthState(
                    state_hash=token_hash(state),
                    account_id=account_id,
                    session_hash=session.token_hash,
                    provider=provider,
                    revision=connection.revision,
                    verifier=self.vault.encrypt(
                        {"account_id": account_id, "provider": provider, "verifier": verifier}
                    ),
                    redirect_uri=redirect,
                    expires=int(time.time()) + 600,
                )
            )
            db.commit()
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {
                "client_id": values["client_id"],
                "redirect_uri": redirect,
                "response_type": "code",
                "scope": " ".join(scopes),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent",
            }
        )

    def finish(self, account_id, token, state, code, *, exchange=None):
        if not isinstance(code, str) or not 1 <= len(code) <= 4096:
            raise ValueError("Invalid authorization code")
        with Session(self.engine) as db:
            begin_academic_write(db)
            session = self.require_session(db, account_id, token)
            saved = db.get(AccountOAuthState, token_hash(state))
            if (
                saved is None
                or saved.account_id != account_id
                or saved.session_hash != session.token_hash
                or saved.expires <= int(time.time())
            ):
                raise PermissionError("Invalid OAuth state")
            provider, revision, redirect = saved.provider, saved.revision, saved.redirect_uri
            connection = db.get(AccountProvider, (account_id, provider))
            if connection is None or connection.revision != revision or not connection.credentials:
                raise PermissionError("Provider configuration changed")
            decoded = self.vault.decrypt(connection.credentials)
            verifier = self.vault.decrypt(saved.verifier)
            if any(
                value.get("account_id") != account_id or value.get("provider") != provider
                for value in (decoded, verifier)
            ):
                raise PermissionError("OAuth owner mismatch")
            values = decoded["values"]
            form = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
                "code_verifier": verifier["verifier"],
            }
            db.delete(saved)
            db.commit()
        if exchange is None:
            from .gmail import GmailService
            from .google_calendar import GoogleCalendarService

            helper = (GmailService if provider == "gmail" else GoogleCalendarService)(
                self.engine, self.vault.directory
            )
            try:
                updated = helper.token_request(values, form)
            finally:
                helper.http.close()
        else:
            updated = exchange(values, form, self.scopes(provider))
        if not updated.get("access_token") or not updated.get("refresh_token"):
            raise ValueError("Offline authorization required")
        with Session(self.engine) as db:
            self.require_session(db, account_id, token)
        self.configure(account_id, provider, updated, expected_revision=revision)
