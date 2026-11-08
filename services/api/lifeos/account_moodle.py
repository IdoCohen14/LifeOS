"""Read-only account-scoped authorized ICS import, using existing feed parser."""

import time
from urllib.parse import urlsplit

import httpx

from .account_providers import AccountProviders
from .google_calendar import GoogleProblem
from .moodle import MAX_BYTES, parse_feed, validate_url


class AccountMoodle(AccountProviders):
    provider = "moodle"
    validate_feed_url = staticmethod(validate_url)
    parse_events = staticmethod(parse_feed)

    def sync(self, account_id, *, client_factory=httpx.Client):
        lease = self.begin_sync(account_id, self.provider)
        http = None
        try:
            url = self.validate_feed_url(lease["credentials"]["url"])
            http = client_factory(timeout=15, follow_redirects=False, trust_env=False)
            chunks, size, started = [], 0, time.monotonic()
            with http.stream(
                "GET",
                url,
                follow_redirects=False,
                timeout=15,
                headers={"Accept": "text/calendar", "Accept-Encoding": "identity"},
            ) as response:
                if response.status_code in (401, 403):
                    raise GoogleProblem("feed_access_denied")
                if response.status_code != 200:
                    raise GoogleProblem("feed_unavailable")
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise GoogleProblem("compressed_feed_not_supported")
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise GoogleProblem("feed_too_large")
                    if time.monotonic() - started > 30:
                        raise GoogleProblem("feed_timeout")
                    chunks.append(chunk)
            events = self.parse_events(b"".join(chunks), urlsplit(url).hostname)
            self.commit_sync(account_id, self.provider, lease["owner"], lease["revision"], events)
        except Exception as error:
            self.abort_sync(
                account_id,
                self.provider,
                lease["owner"],
                lease["revision"],
                error=getattr(error, "code", "provider_unavailable"),
            )
            raise
        finally:
            if http is not None:
                http.close()
        return self.status(account_id, self.provider)
