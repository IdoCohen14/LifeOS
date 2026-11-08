import json
from datetime import date, datetime, timedelta

import pytest
from lifeos.account_preferences import AccountPreferences
from lifeos.account_providers import AccountProviders
from lifeos.account_records import AccountRecords
from lifeos.accounts import AccountService
from lifeos.mail_calendar import candidate
from sqlalchemy.orm import Session


def message(text, subject="מועד הגשה חשוב"):
    return {
        "id": "fixture-mail",
        "thread_id": "fixture-thread",
        "subject": subject,
        "sender": "Teacher <teacher@college.ac.il>",
        "snippet": "Short snippet",
        "calendar_text": text,
        "source_url": "https://mail.google.com/mail/#all/fixture",
        "received_at": 0,
        "labels": ["INBOX"],
    }


def test_only_explicit_critical_full_text_dates_and_real_ranges():
    today = date(2026, 11, 1)
    assert candidate(message("תאריך: 05/11/2026"), "Asia/Jerusalem", today) == {
        "start": "2026-11-05",
        "end": "2026-11-06",
        "all_day": True,
    }
    event = candidate(
        message("תאריך: 05/11/2026 שעות: 08:30–10:00", "פגישה חשובה"), "Asia/Jerusalem", today
    )
    assert event["start"] == "2026-11-05T06:30:00+00:00"
    for text in (
        "תאריך: 05/11/2026 שעה: 08:30",
        "תאריך: 05/11/2026 או 06/11/2026",
        "מחר",
        "תאריך: 05/11/2026 בוטל",
        "תאריך: 31/02/2026",
        "תאריך: 05/11/2025",
    ):
        assert candidate(message(text, "פגישה חשובה"), "Asia/Jerusalem", today) is None
    assert candidate(message("תאריך: 05/11/2026", "עדכון כללי"), "Asia/Jerusalem", today) is None
    only_snippet = message("תאריך: 05/11/2026")
    only_snippet.pop("calendar_text")
    assert candidate(only_snippet, "Asia/Jerusalem", today) is None
    assert candidate(message("Date: 05/11/2026", "Deadline"), "Asia/Jerusalem", today) is None
    assert (
        candidate(
            message("Date: 2026-11-05 Time: 08:30-10:00 PST", "Meeting"), "Asia/Jerusalem", today
        )
        is None
    )


def test_ambiguous_dst_meeting_is_rejected():
    msg = message("Date: 2027-10-31 Time: 01:10-01:40", "Meeting")
    assert candidate(msg, "Asia/Jerusalem", date(2027, 10, 1)) is None


def test_owned_atomic_capture_dedup_respects_deletion_and_does_not_store_body(client, setup_app):
    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    accounts = AccountService(engine, enabled=True)
    owner = accounts.register("mail-calendar", "fixture password")
    other = accounts.register("mail-calendar-other", "fixture password")
    prefs = AccountPreferences(engine)
    current = prefs.get(owner, "mail_calendar")
    prefs.put(owner, "mail_calendar", {"enabled": True}, current["revision"])
    store = AccountProviders(engine, directory)
    store.configure(owner, "gmail", {"refresh_token": "fixture"})
    future = (datetime.now().date() + timedelta(days=7)).isoformat()
    msg = message("Date: " + future, "Assignment deadline")

    def sync():
        lease = store.begin_sync(owner, "gmail")
        store.commit_sync(owner, "gmail", lease["owner"], lease["revision"], [msg])

    sync()
    records = AccountRecords(engine)
    events = records.list(owner, "events")
    assert len(events) == 1
    assert records.list(other, "events") == []
    assert "calendar_text" not in store.records(owner, "gmail")[0]
    sync()
    assert len(records.list(owner, "events")) == 1
    records.delete(owner, "events", events[0]["id"])
    sync()
    assert records.list(owner, "events") == []
    from lifeos.models import AccountPreference

    with Session(engine) as db:
        saved = db.get(AccountPreference, (owner, "mail_calendar"))
        assert len(json.loads(saved.payload)["processed"]) == 1


@pytest.mark.parametrize("mime", ["text/plain", "text/html"])
@pytest.mark.parametrize("enabled", [False, True])
def test_gmail_full_body_is_transient_and_metadata_cache_can_be_upgraded(
    client, setup_app, mime, enabled
):
    import base64

    import httpx
    from lifeos.account_gmail import AccountGmail
    from lifeos.gmail import GmailService

    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    owner = AccountService(engine, enabled=True).register("mail-full", "fixture password")
    prefs = AccountPreferences(engine)
    prefs.put(owner, "mail_calendar", {"enabled": enabled}, 0)
    service = AccountGmail(engine, directory)
    service.configure(
        owner,
        "gmail",
        {"access_token": "fixture", "refresh_token": "fixture", "expires_at": 9999999999},
    )
    body = "Date: " + (datetime.now().date() + timedelta(days=7)).isoformat()
    formats = []

    def handler(request):
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "fixture"}]})
        if request.url.path.endswith("/profile"):
            return httpx.Response(
                200, json={"emailAddress": "fixture@example.test", "historyId": "100"}
            )
        if request.url.path.endswith("/history"):
            return httpx.Response(200, json={"historyId": "100", "history": []})
        formats.append(request.url.params["format"])
        payload = {
            "headers": [
                {"name": "Subject", "value": "Assignment deadline"},
                {"name": "From", "value": "teacher@college.edu"},
            ]
        }
        if request.url.params["format"] == "full":
            text = "<html><body><p>" + body + "</p></body></html>" if mime == "text/html" else body
            payload.update(
                mimeType=mime, body={"data": base64.urlsafe_b64encode(text.encode()).decode()}
            )
        return httpx.Response(
            200,
            json={
                "id": "fixture",
                "threadId": "fixture",
                "internalDate": "1",
                "labelIds": ["INBOX"],
                "payload": payload,
            },
        )

    def factory(engine, directory):
        helper = GmailService(engine, directory)
        helper.http.close()
        helper.http = httpx.Client(transport=httpx.MockTransport(handler))
        return helper

    service.sync(owner, helper_factory=factory)
    expected_formats = ["metadata", "full"] if enabled else ["metadata"]
    assert formats == expected_formats
    assert len(AccountRecords(engine).list(owner, "events")) == int(enabled)
    assert "calendar_text" not in service.records(owner, "gmail")[0]
    service.sync(owner, helper_factory=factory)
    assert formats == expected_formats
