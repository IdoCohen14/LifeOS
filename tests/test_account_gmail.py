import httpx
import pytest
from lifeos.account_gmail import AccountGmail
from lifeos.accounts import AccountService
from lifeos.gmail import GmailService
from lifeos.google_calendar import GoogleProblem
from lifeos.models import AccountProvider
from sqlalchemy.orm import Session


def test_account_gmail_fetches_incrementally_and_keeps_other_account_and_failed_snapshot(
    client, setup_app
):
    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    a = accounts.register("fetch-a", "fixture password a")
    b = accounts.register("fetch-b", "fixture password b")
    service = AccountGmail(engine, setup_app[1])
    phase = [1]
    fail = [False]
    metadata = []

    def handler(request):
        token = request.headers["authorization"].split()[-1]
        path = request.url.path
        if path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "same-id"}]})
        if path.endswith("/profile"):
            return httpx.Response(
                200,
                json={"emailAddress": token + "@example.test", "historyId": str(phase[0] * 100)},
            )
        if path.endswith("/history"):
            return httpx.Response(
                200,
                json={
                    "historyId": str(phase[0] * 100),
                    "history": [{"messages": [{"id": "same-id"}]}] if phase[0] > 1 else [],
                },
            )
        metadata.append(token)
        if fail[0]:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "id": "same-id",
                "threadId": "thread-fixture",
                "internalDate": "1793232000000",
                "labelIds": ["INBOX", "UNREAD"],
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Course " + token},
                        {"name": "From", "value": "fixture@college.edu"},
                    ]
                },
            },
        )

    def helper_factory(engine, directory):
        helper = GmailService(engine, directory)
        helper.http.close()
        helper.http = httpx.Client(transport=httpx.MockTransport(handler))
        return helper

    for owner, token in [(a, "fixture-a"), (b, "fixture-b")]:
        service.configure(
            owner,
            "gmail",
            {"access_token": token, "refresh_token": "fixture-refresh", "expires_at": 9999999999},
        )
        service.sync(owner, helper_factory=helper_factory)
    assert metadata == ["fixture-a", "fixture-b"]
    assert service.records(a, "gmail")[0]["subject"] == "Course fixture-a"
    assert service.records(b, "gmail")[0]["subject"] == "Course fixture-b"
    metadata.clear()
    service.sync(a, helper_factory=helper_factory)
    assert metadata == []
    before = service.records(a, "gmail")
    other = service.records(b, "gmail")
    phase[0] = 2
    fail[0] = True
    with pytest.raises(GoogleProblem):
        service.sync(a, helper_factory=helper_factory)
    assert service.records(a, "gmail") == before and service.records(b, "gmail") == other
    assert service.status(a, "gmail")["syncing"] is False
    failed = service.status(a, "gmail")
    assert failed["error"] == "provider_unavailable" and failed["stale"] is True
    assert failed["next_sync"] > failed["last_attempt"]
    assert service.status(b, "gmail")["error"] is None
    with Session(engine) as db:
        assert db.get(AccountProvider, (a, "gmail")).checkpoint == "100"
