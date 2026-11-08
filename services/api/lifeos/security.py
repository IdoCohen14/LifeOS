import hashlib
import hmac
import json
import os
from pathlib import Path


def initialize_password(directory: Path, password: str):
    if len(password) < 8:
        raise ValueError("Use at least 8 characters")
    if len(password) > 1024:
        raise ValueError("Use at most 1024 characters")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "auth.json"
    if path.exists():
        raise ValueError("Password already configured")
    salt = os.urandom(32)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    with path.open("x", encoding="utf-8") as file:
        json.dump({"salt": salt.hex(), "hash": digest.hex()}, file)


def verify_password(directory: Path, password: str) -> bool:
    try:
        config = json.loads((directory / "auth.json").read_text(encoding="utf-8"))
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(config["salt"]), n=16384, r=8, p=1
        )
        return hmac.compare_digest(digest.hex(), config["hash"])
    except (OSError, ValueError, KeyError):
        return False


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
