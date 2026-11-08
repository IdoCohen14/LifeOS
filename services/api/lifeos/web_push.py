"""Explicit local-owner Web Push registration. GET never generates keys or sends."""

import base64
import hashlib
import time
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .credential_vault import CredentialVault
from .web_push_models import PushConfig, PushDevice
from .web_push_transport import SubscriptionInput, valid_endpoint


def encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class ConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    contact: str = Field(
        min_length=5,
        max_length=254,
        pattern=r"^[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$",
    )
    revision: int = Field(ge=0, le=2147483647)


class Lookup(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    endpoint: str = Field(min_length=30, max_length=2200)

    @field_validator("endpoint")
    @classmethod
    def valid(cls, value):
        return valid_endpoint(value)


def public_config(row):
    return {
        "configured": bool(row),
        "public_key": row.public_key if row else None,
        "contact": row.contact if row else "",
        "revision": row.revision if row else 0,
    }


def device_status(row):
    return {"id": row.id, "enabled": row.enabled, "last_error": row.last_error}


class WebPushService:
    def apple_vapid_headers(self, key, contact, audience):
        """Reuse an encrypted sender JWT across requests and process restarts."""
        from urllib.parse import urlsplit

        from py_vapid import Vapid

        target = urlsplit(valid_endpoint(audience + "/vapid-audience-check"))
        if not target.hostname.endswith(".push.apple.com") or audience != "https://" + target.hostname:
            raise ValueError("push_endpoint_unsupported")

        PushConfig, _ = self.models
        now = int(time.time())
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            self.authorize(db)
            row = db.get(PushConfig, self.config_id)
            if row is None or row.contact != contact:
                raise ValueError("push_config_changed")
            payload = self.open(row.private_key)
            if payload["key"] != key:
                raise ValueError("push_config_changed")
            cache = {host: value for host, value in payload.get("apple_vapid", {}).items()
                     if value["expires"] > now + 60 and value["contact"] == contact}
            cached = cache.get(audience)
            if cached:
                return dict(cached["headers"])
            if len(cache) >= 32:
                raise ValueError("push_vapid_cache_limit")
            expires = now + 12 * 60 * 60
            headers = Vapid.from_string(private_key=key).sign(
                {"sub": "mailto:" + contact, "aud": audience, "exp": expires})
            cache[audience] = {"contact": contact, "expires": expires, "headers": headers}
            payload["apple_vapid"] = cache
            row.private_key = self.seal(payload)
            db.commit()
            return dict(headers)

    def __init__(self, engine, directory, *, account_id=None):
        self.engine, self.directory = engine, directory
        self.vault = CredentialVault(directory)
        self.account_id = account_id
        from .web_push_models import AccountPushConfig, AccountPushDevice

        self.models = (
            (AccountPushConfig, AccountPushDevice) if account_id else (PushConfig, PushDevice)
        )
        self.config_id = account_id if account_id else 1

    def authorize(self, db):
        if self.account_id is not None:
            from .account_records import AccountRecords

            AccountRecords(self.engine).authorize(db, self.account_id)

    def device_scope(self, model):
        return model.account_id == self.account_id if self.account_id is not None else True

    def seal(self, value):
        if self.account_id is not None:
            value = {"account_id": self.account_id, "values": value}
        return self.vault.encrypt(value)

    def open(self, value):
        payload = self.vault.decrypt(value)
        if self.account_id is not None:
            if payload.get("account_id") != self.account_id:
                raise ValueError("Push owner mismatch")
            return payload["values"]
        return payload

    def config(self):
        PushConfig, PushDevice = self.models
        with Session(self.engine) as db:
            self.authorize(db)
            return public_config(db.get(PushConfig, self.config_id))

    def configure(self, body):
        PushConfig, PushDevice = self.models
        with Session(self.engine) as db:
            self.authorize(db)
            db.execute(text("BEGIN IMMEDIATE"))
            row = db.get(PushConfig, self.config_id)
            if body.revision != (row.revision if row else 0):
                raise HTTPException(409, "push_config_changed")
            if row is None:
                private = ec.generate_private_key(ec.SECP256R1())
                key = encode(
                    private.private_bytes(
                        serialization.Encoding.DER,
                        serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption(),
                    )
                )
                row = PushConfig(
                    id=self.config_id,
                    private_key=self.seal({"key": key}),
                    public_key=encode(
                        private.public_key().public_bytes(
                            serialization.Encoding.X962,
                            serialization.PublicFormat.UncompressedPoint,
                        )
                    ),
                    contact=body.contact,
                    revision=0,
                )
                db.add(row)
            row.contact, row.revision = body.contact, body.revision + 1
            db.flush()
            result = public_config(row)
            db.commit()
            return result

    def register(self, body):
        now = time.time()
        if body.expirationTime is not None and body.expirationTime <= now * 1000:
            raise HTTPException(422, "push_subscription_expired")
        endpoint_hash = hashlib.sha256(body.endpoint.encode()).hexdigest()
        value = body.model_dump()
        PushConfig, PushDevice = self.models
        with Session(self.engine) as db:
            self.authorize(db)
            db.execute(text("BEGIN IMMEDIATE"))
            if db.get(PushConfig, self.config_id) is None:
                raise HTTPException(409, "push_setup_required")
            db.execute(
                delete(PushDevice).where(
                    self.device_scope(PushDevice), PushDevice.last_seen < now - 90 * 86400
                )
            )
            row = db.scalar(
                select(PushDevice).where(
                    self.device_scope(PushDevice), PushDevice.endpoint_hash == endpoint_hash
                )
            )
            if row is None:
                count = db.scalar(
                    select(func.count())
                    .select_from(PushDevice)
                    .where(self.device_scope(PushDevice))
                )
                if count >= 5:
                    raise HTTPException(429, "push_device_limit")
                row = PushDevice(
                    id=str(uuid4()),
                    **({"account_id": self.account_id} if self.account_id is not None else {}),
                    endpoint_hash=endpoint_hash,
                    subscription=self.seal(value),
                    last_seen=now,
                    generation=1,
                    enabled=True,
                )
                db.add(row)
            else:
                if not row.enabled or self.open(row.subscription) != value:
                    row.generation += 1
                    row.subscription = self.seal(value)
                    row.cooldown_until = 0
                row.enabled, row.last_error, row.last_seen = True, None, now
            db.flush()
            result = device_status(row)
            db.commit()
            return result

    def lookup(self, endpoint):
        digest = hashlib.sha256(endpoint.encode()).hexdigest()
        PushConfig, PushDevice = self.models
        with Session(self.engine) as db:
            self.authorize(db)
            row = db.scalar(
                select(PushDevice).where(
                    self.device_scope(PushDevice), PushDevice.endpoint_hash == digest
                )
            )
            return device_status(row) if row else None

    def devices(self):
        PushConfig, PushDevice = self.models
        with Session(self.engine) as db:
            self.authorize(db)
            return [
                {**device_status(row), "registered_at": row.last_seen}
                for row in db.scalars(
                    select(PushDevice)
                    .where(self.device_scope(PushDevice))
                    .order_by(PushDevice.last_seen.desc())
                    .limit(5)
                )
            ]

    def status(self, id):
        PushConfig, PushDevice = self.models
        with Session(self.engine) as db:
            self.authorize(db)
            row = db.get(PushDevice, id)
            if row is None or self.account_id is not None and row.account_id != self.account_id:
                raise HTTPException(404, "push_device_missing")
            return device_status(row)

    def remove(self, id):
        PushConfig, PushDevice = self.models
        with Session(self.engine) as db:
            self.authorize(db)
            db.execute(text("BEGIN IMMEDIATE"))
            row = db.get(PushDevice, id)
            if row and (self.account_id is None or row.account_id == self.account_id):
                db.delete(row)
            db.commit()


def web_push_router(engine, directory, authenticated):
    service = WebPushService(engine, directory)
    router = APIRouter(prefix="/push", dependencies=[Depends(authenticated)])

    @router.get("/config")
    def config():
        return service.config()

    @router.put("/config")
    def configure(body: ConfigInput):
        return service.configure(body)

    @router.get("/subscriptions")
    def devices():
        return service.devices()

    @router.post("/subscriptions")
    def register(body: SubscriptionInput):
        return service.register(body)

    @router.post("/lookup")
    def lookup(body: Lookup):
        return service.lookup(body.endpoint)

    @router.get("/subscriptions/{id}")
    def status(id: str):
        return service.status(id)

    @router.delete("/subscriptions/{id}", status_code=204)
    def remove(id: str):
        service.remove(id)

    return router
