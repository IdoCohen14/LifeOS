"""Internal metadata inspection only; candidates are never permission to delete."""

import os
import stat
import time
from uuid import UUID

from sqlalchemy.orm import Session

from .account_archive import AccountArchive
from .data_lock import account_storage_lock, runtime_lock


class AccountPartialInventory(AccountArchive):
    def inspect(self, account_id, *, max_entries=500):
        if type(max_entries) is not int or not 1 <= max_entries <= 500:
            raise ValueError("Invalid inventory limit")
        if not self.directory.is_dir():
            raise ValueError("Data directory unavailable")
        result = {
            "partials": [], "scanned": 0, "truncated": False,
            "deletion_authorized": False, "contents_verified": False,
        }
        with runtime_lock(self.directory), Session(self.engine) as db:
            self.authorize(db, account_id)
            with account_storage_lock(self.directory, account_id):
                folder = self.folder(account_id)
                if not folder.exists():
                    return result
                started, now = time.monotonic(), time.time_ns()
                with os.scandir(folder) as entries:
                    for entry in entries:
                        if result["scanned"] >= max_entries or time.monotonic() - started > 2:
                            result["truncated"] = True
                            break
                        result["scanned"] += 1
                        if not entry.name.endswith(".partial"):
                            continue
                        identity = entry.name.removesuffix(".partial")
                        try:
                            if str(UUID(identity)) != identity:
                                continue
                            # Windows DirEntry.stat may report st_nlink=0 from cached
                            # directory metadata; os.stat obtains the actual link count.
                            info = os.stat(entry.path, follow_symlinks=False)
                        except (ValueError, OSError):
                            continue
                        if (
                            not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                            or getattr(info, "st_file_attributes", 0)
                            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                        ):
                            continue
                        result["partials"].append({
                            "name": entry.name,
                            "size_bytes": info.st_size,
                            "modified_ns": info.st_mtime_ns,
                            "future_timestamp": info.st_mtime_ns > now,
                            "older_than_24h": now - info.st_mtime_ns >= 86400 * 10**9,
                        })
        result["partials"].sort(key=lambda row: row["name"])
        return result
