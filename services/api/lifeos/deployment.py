"""Explicit local/server settings. Public origins never come from request headers."""

import ipaddress
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from .db import ROOT


def public_origin(value):
    try:
        if not value or not value.isascii() or value != value.strip() or any(ord(c) < 33 for c in value):
            raise ValueError()
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or "?" in value or "#" in value or not host
                or len(host) > 253 or "." not in host
                or not re.fullmatch(r"[a-z]{2,63}|xn--[a-z0-9-]{2,59}", host.split(".")[-1])
                or host.endswith((".local", ".localhost", ".internal"))
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split("."))
                or port is not None and not 1 <= port <= 65535):
            raise ValueError()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError()
        return "https://" + host + (":" + str(port) if port not in (None, 443) else "")
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Invalid HTTPS public origin") from None


def port(value):
    if not re.fullmatch(r"[0-9]+", value) or not 1024 <= int(value) <= 65535:
        raise ValueError("Invalid loopback service port")
    return int(value)


@dataclass(frozen=True)
class DeploymentConfig:
    mode: str
    origin: str
    web_port: int
    api_port: int
    pilot_owner_id: str | None = None
    private_pc_assistant: bool = False

    def allows_account(self, account_id):
        return self.pilot_owner_id is None or account_id == self.pilot_owner_id

    @property
    def server(self):
        return self.mode == "server"

    @property
    def secure_cookies(self):
        return self.server

    @property
    def assistant_enabled(self):
        return not self.server or (self.private_pc_assistant and self.pilot_owner_id is not None)

    def oauth_callback(self, web_port=None):
        origin = self.origin if self.server else "http://127.0.0.1:" + str(port(str(self.web_port if web_port is None else web_port)))
        return origin + "/api/accounts/oauth/callback"

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        mode = env.get("LIFEOS_DEPLOYMENT_MODE", "local")
        if mode not in ("local", "server"):
            raise ValueError("Unknown deployment mode")
        web, api = port(env.get("LIFEOS_WEB_PORT", "3000")), port(env.get("LIFEOS_API_PORT", "8765"))
        if web == api:
            raise ValueError("Service ports must differ")
        value = env.get("LIFEOS_PUBLIC_ORIGIN", "")
        pilot = env.get("LIFEOS_PILOT_OWNER_ID") or None
        if pilot:
            if mode != "server" or str(UUID(pilot)) != pilot:
                raise ValueError("Pilot owner requires server mode and a canonical UUID")
        if mode == "server":
            origin = public_origin(value)
            directory = Path(env.get("LIFEOS_DATA_DIR", ""))
            if not directory.is_absolute():
                raise ValueError("Server data directory must be explicit and absolute")
            resolved = directory.resolve()
            if resolved.is_relative_to(ROOT) and not (
                env.get("LIFEOS_TEST_MODE") == "1" and resolved.is_relative_to(ROOT / ".runtime")
            ):
                raise ValueError("Server data must stay outside source; fixtures only in .runtime")
        else:
            if value:
                raise ValueError("Public origin requires explicit server mode")
            origin = f"http://127.0.0.1:{web}"
        assistant = env.get("LIFEOS_PRIVATE_PC_ASSISTANT", "0")
        if assistant not in {"0", "1"}:
            raise ValueError("Invalid private PC assistant flag")
        if assistant == "1" and (mode != "server" or not pilot
                                  or not urlsplit(origin).hostname.endswith(".ts.net")):
            raise ValueError("Private PC assistant requires a single-owner Tailscale server")
        return cls(mode, origin, web, api, pilot, assistant == "1")
