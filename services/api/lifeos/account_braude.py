"""Official Braude student-portal calendar subscription; no portal login scraping."""

import hashlib
import re
from urllib.parse import parse_qs, urlsplit

from icalendar import Calendar

from .account_moodle import AccountMoodle
from .google_calendar import GoogleProblem
from .moodle import parse_feed


def validate_portal_url(value):
    try:
        parsed = urlsplit(value)
        query = parse_qs(parsed.query, keep_blank_values=True)
        required = {"prgname", "Google_InnerID", "Google_Token", "Google_Population"}
        if (not isinstance(value, str) or len(value) > 8192
                or any(ord(c) < 33 for c in value) or not value.isascii()
                or parsed.scheme != "https" or parsed.hostname != "info.braude.ac.il"
                or parsed.port not in (None, 443) or parsed.username or parsed.password
                or parsed.fragment or parsed.path.lower() != "/yedion/fireflyweb.aspx"
                or set(query) != required or any(len(v) != 1 or not v[0] for v in query.values())
                or query["prgname"] != ["PublicHours"]
                or query["Google_Population"] != ["S"]):
            raise ValueError()
    except Exception:
        raise GoogleProblem("invalid_portal_url", 422) from None
    return value


def parse_portal_feed(content, host):
    # Yedion publishes refresh metadata as P6H instead of RFC5545's PT6H.
    # Normalize only those metadata fields, never event dates or durations.
    content = re.sub(
        rb"(?m)^((?:REFRESH-INTERVAL;VALUE=DURATION|X-PUBLISHED-TTL):)P([0-9]+H(?:[0-9]+M)?)\r?$",
        rb"\1PT\2\r", content,
    )
    events = parse_feed(content, host)
    locations = {"moodle-" + hashlib.sha256((host + "\0" + str(event["UID"])).encode()).hexdigest():
                 str(event.get("LOCATION", ""))[:240]
                 for event in Calendar.from_ical(content).walk("VEVENT")}
    return [{**event, "id": event["id"].replace("moodle-", "braude-", 1),
             "notes": event["notes"] + ("\nחדר: " + locations[event["id"]] if locations.get(event["id"]) else ""),
             "source": "braude", "source_url": "https://info.braude.ac.il/"}
            for event in events]


class AccountBraude(AccountMoodle):
    provider = "braude"
    validate_feed_url = staticmethod(validate_portal_url)
    parse_events = staticmethod(parse_portal_feed)
