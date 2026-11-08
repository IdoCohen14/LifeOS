"""Allowlisted encrypted Web Push; discard provider bodies, redirects and proxy env."""

import base64
import http.client
import json
import re
import ssl
from types import SimpleNamespace
from urllib.parse import urlsplit

import certifi
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def decode(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
        raise ValueError("push_key_invalid")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def valid_endpoint(value):
    try:
        target = urlsplit(value)
        if (
            not value.isascii()
            or any(c.isspace() for c in value)
            or target.scheme != "https"
            or target.port not in (None, 443)
            or target.username
            or target.password
            or target.query
            or target.fragment
        ):
            raise ValueError("push_endpoint_unsupported")
        paths = {
            "fcm.googleapis.com": r"/(?:fcm/send|wp)/[A-Za-z0-9_:.-]{8,2048}",
            "updates.push.services.mozilla.com": r"/(?:wpush/v2|push/v1)/[A-Za-z0-9_:.=-]{8,2048}",
        }
        # Apple documents *.push.apple.com; allow only DNS labels within it.
        if len(target.hostname or "") <= 253 and re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+push\.apple\.com", target.hostname or ""):
            paths[target.hostname] = r"/[A-Za-z0-9_:.=-]{8,2048}"
        if target.hostname not in paths or not re.fullmatch(paths[target.hostname], target.path):
            raise ValueError("push_endpoint_unsupported")
    except (ValueError, TypeError):
        raise ValueError("push_endpoint_unsupported") from None
    return value


class SubscriptionKeys(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    p256dh: str = Field(min_length=80, max_length=90)
    auth: str = Field(min_length=20, max_length=26)

    @model_validator(mode="after")
    def valid_keys(self):
        key, auth = decode(self.p256dh), decode(self.auth)
        if len(key) != 65 or len(auth) != 16:
            raise ValueError("push_key_invalid")
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), key)
        return self


class SubscriptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    endpoint: str = Field(min_length=30, max_length=2200)
    keys: SubscriptionKeys
    expirationTime: float | None = Field(default=None, ge=0)

    @field_validator("endpoint")
    @classmethod
    def endpoint_valid(cls, value):
        return valid_endpoint(value)


class PushSession:
    def __init__(self, connection_factory):
        self.connection_factory = connection_factory

    def post(self, endpoint, *, data, headers, timeout):
        valid_endpoint(endpoint)
        target = urlsplit(endpoint)
        # Match the CA bundle used by our existing HTTP clients; portable Python
        # on Windows may not contain Apple's issuer in its default trust store.
        context = ssl.create_default_context(cafile=certifi.where())
        context.set_alpn_protocols(["http/1.1"])
        connection = self.connection_factory(target.hostname, port=443, timeout=10, context=context)
        connection.set_debuglevel(0)
        response = None
        try:
            connection.request("POST", target.path, body=data, headers=headers)
            response = connection.getresponse()
            retry = response.getheader("retry-after", "")
            return SimpleNamespace(
                status_code=response.status,
                reason="",
                text="",
                headers={"Retry-After": retry if retry.isdigit() and len(retry) <= 6 else "300"},
            )
        finally:
            if response is not None:
                response.close()
            connection.close()


def send_push(subscription, private_key, contact, payload, *, connection_factory=None, vapid_headers=None):
    from pywebpush import WebPushException, webpush

    value = SubscriptionInput.model_validate(subscription).model_dump()
    apple = urlsplit(value["endpoint"]).hostname.endswith(".push.apple.com")
    if apple and not vapid_headers:
        raise ValueError("apple_vapid_cache_required")
    raw = json.dumps({**payload, "visible_required": True} if apple else payload, separators=(",", ":"), ensure_ascii=False)
    if len(raw.encode()) > 1024:
        raise ValueError("push_payload_limit")
    try:
        result = webpush(
            subscription_info=value,
            data=raw,
            vapid_private_key=None if apple else private_key,
            vapid_claims=None if apple else {"sub": "mailto:" + contact},
            headers=vapid_headers if apple else None,
            content_encoding="aes128gcm",
            # Apple must display every delivered push; avoid offline queuing.
            ttl=0 if apple else 300,
            timeout=10,
            verbose=False,
            requests_session=PushSession(connection_factory or http.client.HTTPSConnection),
        )
        code = result.status_code
        retry = result.headers.get("Retry-After", "300")
    except WebPushException as error:
        code = error.status_code or 0
        retry = (
            error.response.headers.get("Retry-After", "300")
            if error.response is not None
            else "300"
        )
    except (OSError, http.client.HTTPException, ValueError):
        return 0, 300
    return code, min(3600, max(300, int(retry))) if str(retry).isdigit() else 300
