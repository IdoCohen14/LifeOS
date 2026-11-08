"""OS lifetime locks: one launcher, shared data users, exclusive offline recovery."""

import os
from contextlib import contextmanager


def _windows_lock(handle, shared):
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    lock = kernel.LockFileEx
    lock.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(Overlapped),
    ]
    lock.restype = wintypes.BOOL
    flags = 1 if shared else 3  # FAIL_IMMEDIATELY; optionally EXCLUSIVE_LOCK.
    if not lock(msvcrt.get_osfhandle(handle.fileno()), flags, 0, 1, 0, ctypes.byref(Overlapped())):
        raise ctypes.WinError(ctypes.get_last_error())


@contextmanager
def _file_lock(path, *, shared=False, error="close_lifeos_before_recovery"):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                _windows_lock(handle, shared)
            else:
                import fcntl

                mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
                fcntl.flock(handle.fileno(), mode | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError(error) from None
        yield
    finally:
        handle.close()


@contextmanager
def launcher_lock(directory):
    with _file_lock(directory / ".lifeos.lock"):
        yield


@contextmanager
def runtime_lock(directory):
    with _file_lock(directory / ".lifeos-runtime.lock", shared=True):
        if (directory / ".restore-in-progress").exists():
            raise RuntimeError("complete_recovery_before_starting_lifeos")
        yield


@contextmanager
def data_lock(directory):
    with launcher_lock(directory), _file_lock(directory / ".lifeos-runtime.lock"):
        yield


@contextmanager
def backup_lock(directory):
    with _file_lock(directory / ".lifeos-backup.lock", error="backup_in_progress"):
        yield


@contextmanager
def account_storage_lock(directory, account_id):
    from uuid import UUID

    if str(UUID(account_id)) != account_id:
        raise ValueError("Invalid account identity")
    with _file_lock(directory / "account-locks" / (account_id + ".lock"), error="account_storage_busy"):
        yield
