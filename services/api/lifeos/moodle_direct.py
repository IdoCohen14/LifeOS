"""Read-only Braude mobile API proof. No password collection or credential logging."""

import base64
import hashlib
import hmac
import json
import re
from urllib.parse import urlencode

import httpx

ORIGIN = "https://moodle27.braude.ac.il"
SCHEME = "lifeosmoodle"
MAX_RESPONSE = 2 * 1024 * 1024


def launch_url(passport):
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", passport):
        raise ValueError("Invalid login state")
    return ORIGIN + "/admin/tool/mobile/launch.php?" + urlencode(
        {"service": "moodle_mobile_app", "passport": passport, "urlscheme": SCHEME,
         "confirmed": 1}
    )


def callback_token(callback, passport):
    launch_url(passport)
    prefix = SCHEME + "://token="
    if not isinstance(callback, str) or not callback.startswith(prefix) or len(callback) > 8192:
        raise ValueError("Invalid login response")
    try:
        encoded = callback[len(prefix):]
        # Windows URL dispatch appends an authority-closing slash. Only remove
        # that extra character; never trim a valid base64 alphabet character.
        if encoded.endswith("/") and len(encoded) % 4 == 1:
            encoded = encoded[:-1]
        decoded = base64.b64decode(encoded, validate=True).decode("ascii")
        parts = decoded.split(":::")
        expected = hashlib.md5((ORIGIN + passport).encode(), usedforsecurity=False).hexdigest()
        if len(parts) not in (2, 3) or not hmac.compare_digest(parts[0], expected):
            raise ValueError()
        if not re.fullmatch(r"[a-fA-F0-9]{32}", parts[1]):
            raise ValueError()
        return parts[1]  # Never retain the optional Moodle private auto-login token.
    except Exception:
        raise ValueError("Invalid login response") from None


class MoodleDirectClient:
    def __init__(self, token, *, transport=None):
        if not isinstance(token, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", token):
            raise ValueError("Invalid access key")
        self.token, self.transport = token, transport

    def read(self, function, **arguments):
        if function not in {"core_webservice_get_site_info", "core_enrol_get_users_courses"}:
            raise ValueError("Read function not allowed")
        try:
            with httpx.Client(
                timeout=20, follow_redirects=False, trust_env=False, transport=self.transport
            ) as client:
                with client.stream(
                    "POST", ORIGIN + "/webservice/rest/server.php",
                    data={"wstoken": self.token, "wsfunction": function,
                          "moodlewsrestformat": "json", **arguments},
                    headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                ) as response:
                    if response.status_code != 200:
                        raise ValueError()
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_RESPONSE:
                            raise ValueError()
                        chunks.append(chunk)
            value = json.loads(b"".join(chunks))
            if isinstance(value, dict) and ("exception" in value or "errorcode" in value):
                raise ValueError()
            return value
        except Exception:
            # Upstream errors can echo tokens, URLs or personal information.
            raise ValueError("Moodle read unavailable or not authorized") from None

    def courses(self):
        site = self.read("core_webservice_get_site_info")
        if not isinstance(site, dict) or site.get("siteurl", "").rstrip("/") != ORIGIN:
            raise ValueError("Unexpected Moodle identity")
        user = site.get("userid")
        if type(user) is not int or user <= 0:
            raise ValueError("Unexpected Moodle identity")
        functions = {f.get("name") for f in site.get("functions", []) if isinstance(f, dict)}
        if "core_enrol_get_users_courses" not in functions:
            raise ValueError("Course reading not authorized")
        courses = self.read("core_enrol_get_users_courses", userid=user)
        if not isinstance(courses, list) or len(courses) > 2000:
            raise ValueError("Invalid course response")
        result, seen = [], set()
        for course in courses:
            if (not isinstance(course, dict) or type(course.get("id")) is not int
                    or course["id"] <= 0 or course["id"] in seen
                    or not isinstance(course.get("fullname"), str)):
                raise ValueError("Invalid course response")
            seen.add(course["id"])
            item = {"id": course["id"], "name": course["fullname"][:500]}
            for key in ("shortname", "category", "startdate", "enddate", "visible"):
                value = course.get(key)
                if type(value) in (str, int, bool):
                    item[key] = value[:500] if isinstance(value, str) else value
            result.append(item)
        return result
