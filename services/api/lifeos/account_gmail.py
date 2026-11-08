"""Read-only Gmail fetcher using isolated account state and atomic fences."""

import re
import time
from urllib.parse import quote

from .account_preferences import AccountPreferences
from .account_providers import AccountProviders
from .gmail import API, GmailService
from .gmail_history import history_changes, history_id
from .gmail_metadata import parse_message
from .google_calendar import GoogleProblem
from .mail_body import calendar_text
from .mail_calendar import CRITICAL


class AccountGmail(AccountProviders):
    def sync(self, account_id, *, helper_factory=GmailService):
        lease = self.begin_sync(account_id, "gmail")
        helper = None
        values = lease["credentials"]
        started = time.monotonic()

        def get(path, params=None):
            nonlocal values
            if time.monotonic() - started > 120:
                raise GoogleProblem("provider_response_timeout")
            response = helper._request(
                "GET",
                API + path,
                max_bytes=128 * 1024,
                params=params,
                headers={"Authorization": "Bearer " + values["access_token"]},
            )
            if response.status_code == 401:
                values = helper.token_request(
                    values,
                    {"grant_type": "refresh_token", "refresh_token": values["refresh_token"]},
                )
                response = helper._request(
                    "GET",
                    API + path,
                    max_bytes=128 * 1024,
                    params=params,
                    headers={"Authorization": "Bearer " + values["access_token"]},
                )
            if time.monotonic() - started > 120:
                raise GoogleProblem("provider_response_timeout")
            if response.status_code == 404:
                return None
            if response.status_code in (401, 403):
                raise GoogleProblem("reauthorization_required", 409)
            if response.status_code == 429:
                raise GoogleProblem("rate_limited")
            if not response.is_success:
                raise GoogleProblem("provider_unavailable")
            return response.json()

        try:
            helper = helper_factory(self.engine, self.vault.directory)
            if not values.get("refresh_token"):
                raise GoogleProblem("not_connected", 409)
            if values.get("expires_at", 0) <= int(time.time()) + 60:
                values = helper.token_request(
                    values,
                    {"grant_type": "refresh_token", "refresh_token": values["refresh_token"]},
                )
            listing = get("/messages", {"labelIds": "INBOX", "maxResults": 50})
            if not isinstance(listing, dict) or not isinstance(listing.get("messages", []), list):
                raise GoogleProblem("invalid_provider_response")
            profile = get("/profile")
            email = profile.get("emailAddress") if isinstance(profile, dict) else None
            if not isinstance(email, str) or not email:
                raise GoogleProblem("invalid_provider_response")
            cached = {row["id"]: row for row in self.records(account_id, "gmail")}
            delta = history_changes(get, lease["checkpoint"])
            checkpoint = delta[1] if delta else history_id(profile.get("historyId"))
            prefix = "https://mail.google.com/mail/?authuser=" + quote(email, safe="") + "#all/"
            staged = []
            auto_calendar = AccountPreferences(self.engine).get(account_id, "mail_calendar")["values"]["enabled"]
            for entry in listing.get("messages", [])[:50]:
                mid = entry.get("id") if isinstance(entry, dict) else None
                if not isinstance(mid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", mid):
                    raise GoogleProblem("invalid_provider_response")
                if (
                    delta is not None
                    and mid not in delta[0]
                    and mid in cached
                    and "thread_id" in cached[mid]
                    and (not auto_calendar or cached[mid].get("calendar_checked"))
                ):
                    staged.append({**cached[mid], "source_url": prefix + mid})
                    continue
                message = get(
                    "/messages/" + mid,
                    {
                        "format": "metadata",
                        "metadataHeaders": [
                            "Subject",
                            "From",
                            "List-Unsubscribe",
                            "Auto-Submitted",
                            "Precedence",
                        ],
                    },
                )
                if message is None:
                    continue
                if not isinstance(message, dict):
                    raise GoogleProblem("invalid_provider_response")
                if "INBOX" in message.get("labelIds", []):
                    parsed = parse_message(message, mid, prefix)
                    parsed["calendar_checked"] = bool(auto_calendar and not CRITICAL.search(parsed["subject"]))
                    if auto_calendar and CRITICAL.search(parsed["subject"]):
                        try:
                            full = get("/messages/" + mid, {"format": "full"})
                            text = calendar_text(full.get("payload", {})) if isinstance(full, dict) else None
                            if text:
                                parsed["calendar_text"] = text
                                parsed["calendar_checked"] = True
                        except Exception:
                            pass  # No event inferred from unavailable/unsupported message body.
                    staged.append(parsed)
            self.commit_sync(
                account_id,
                "gmail",
                lease["owner"],
                lease["revision"],
                staged,
                checkpoint,
                credentials=values,
            )
        except Exception as error:
            self.abort_sync(
                account_id,
                "gmail",
                lease["owner"],
                lease["revision"],
                error=getattr(error, "code", "provider_unavailable"),
            )
            raise
        finally:
            if helper is not None:
                helper.http.close()
        return self.status(account_id, "gmail")
