"""Encrypted provider secrets: Windows user-bound DPAPI, POSIX private Fernet key."""

import ctypes
import json
import os
from pathlib import Path


def dpapi(data: bytes, decrypt=False):
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    name = "CryptUnprotectData" if decrypt else "CryptProtectData"
    method = getattr(crypt, name)
    method.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    method.restype = wintypes.BOOL
    if not method(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ValueError("Credential encryption unavailable for this OS account")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


class CredentialVault:
    def __init__(self, directory: Path):
        self.directory = directory

    def fernet(self):
        from cryptography.fernet import Fernet

        path = self.directory / "provider.key"
        if not path.exists():
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "wb") as file:
                    file.write(Fernet.generate_key())
            except FileExistsError:
                pass
        if path.stat().st_mode & 0o077:
            raise ValueError("Provider key permissions must be 0600")
        return Fernet(path.read_bytes())

    def encrypt(self, value: dict) -> bytes:
        raw = json.dumps(value).encode()
        return b"DP1" + dpapi(raw) if os.name == "nt" else b"FE1" + self.fernet().encrypt(raw)

    def decrypt(self, value: bytes) -> dict:
        if value.startswith(b"DP1") and os.name == "nt":
            raw = dpapi(value[3:], True)
        elif value.startswith(b"FE1"):
            raw = self.fernet().decrypt(value[3:])
        else:
            raise ValueError("Credential belongs to another platform")
        return json.loads(raw)
