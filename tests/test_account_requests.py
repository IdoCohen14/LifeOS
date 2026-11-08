import time

import pytest
from lifeos.account_notices import AccountNotices
from lifeos.account_records import AccountRecords
from lifeos.account_requests import AccountRequests
from lifeos.accounts import AccountService
from lifeos.models import AccountPreference
from lifeos.request_models import RequestState
from sqlalchemy.orm import Session


def fixture(setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owner = auth.register("request-owner", "fixture password")
    other = auth.register("request-other", "fixture password")
    task = AccountRecords(engine).save(
        owner, "tasks", {"title": "Tracked fixture", "due": "2000-01-01"}
    )
    notice = AccountNotices(engine).feed(owner)["items"][0]
    return engine, owner, other, task, notice


def test_owned_deduplicated_versioned_tracking_does_not_complete_task(client, setup_app):
    engine, owner, other, task, notice = fixture(setup_app)
    requests = AccountRequests(engine)
    item = requests.create(owner, notice["id"])
    assert requests.create(owner, notice["id"])["id"] == item["id"]
    with pytest.raises(LookupError):
        requests.create(other, notice["id"])
    with pytest.raises(LookupError):
        requests.get(other, item["id"])
    changed = requests.update(owner, item["id"], {"version": 1, "followup_minutes": 60})
    assert changed["followup_at"] > time.time()
    with pytest.raises(ValueError):
        requests.update(owner, item["id"], {"version": 1, "status": "done"})
    assert not requests.result(owner, item["id"], 1, None)
    requests.update(owner, item["id"], {"version": 2, "status": "done"})
    assert not requests.candidates(owner)
    requests.delete(owner, item["id"], 3)
    assert not requests.listing(owner)["items"]
    assert AccountRecords(engine).list(owner, "tasks")[0]["id"] == task["id"]
    assert not AccountRecords(engine).list(owner, "tasks")[0]["completed"]


def test_followup_uses_existing_feed_receipts_and_preferences(client, setup_app):
    engine, owner, _, _, notice = fixture(setup_app)
    requests = AccountRequests(engine)
    item = requests.create(owner, notice["id"])
    with Session(engine) as db:
        row = db.get(AccountPreference, (owner, "assistant_requests"))
        state = RequestState.model_validate_json(row.payload)
        state.items[0].followup_at = int(time.time()) - 1
        row.payload = state.model_dump_json()
        db.commit()
    feed = AccountNotices(engine)
    followup = next(row for row in feed.feed(owner)["items"] if row["kind"] == "request_followup")
    assert followup["request_id"] == item["id"]
    feed.mutate(owner, read_ids=[followup["id"]])
    assert requests.get(owner, item["id"])["status"] == "waiting_user"
    requests.update(owner, item["id"], {"version": 1, "status": "done"})
    assert all(row["kind"] != "request_followup" for row in feed.feed(owner)["items"])


def test_request_context_is_owned_and_archive_preserves_metadata_without_chat(client, setup_app):
    import json

    from lifeos.account_archive import AccountArchive
    from lifeos.account_conversation import AccountConversation
    from lifeos.account_restore import AccountRestore

    engine, owner, other, _, notice = fixture(setup_app)
    requests = AccountRequests(engine)
    item = requests.create(owner, notice["id"])
    assert requests.context(owner, item["id"], 1)["title"] == "Tracked fixture"
    with pytest.raises(LookupError):
        requests.context(other, item["id"], 1)
    archive = AccountArchive(engine, setup_app[1])
    exported = json.loads(archive.export(owner))["tables"]
    preference = next(
        row for row in exported["account_preferences"] if row["kind"] == "assistant_requests"
    )
    assert RequestState.model_validate_json(preference["payload"]).items[0].id == item["id"]
    assert not AccountConversation(engine).history(owner)["enabled"]
    restore = AccountRestore(engine, setup_app[1])
    token = AccountService(engine, enabled=True).login("request-owner", "fixture password")["token"]
    backup = restore.create(owner, "fixture backup password")
    requests.delete(owner, item["id"], 1)
    preview = restore.preview(owner, token, backup["id"], "fixture backup password")
    restore.confirm(owner, token, preview["id"], "fixture backup password")
    assert requests.get(owner, item["id"])["status"] == "waiting_user"


def test_request_chat_and_confirm_routes_preserve_history_opt_in(setup_app, monkeypatch):
    import json

    import httpx
    from fastapi.testclient import TestClient

    monkeypatch.setenv("LIFEOS_ACCOUNT_MODE", "1")
    app = setup_app[2]()
    captured = []

    def infer(payload):
        captured.append(payload)
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {"action": "task", "title": "Confirmed fixture", "date": "2026-11-09"}
                    )
                }
            },
        )

    app.state.assistant.infer = infer
    with TestClient(
        app, base_url="http://127.0.0.1:8000", headers={"X-LifeOS-Key": "test-process-key"}
    ) as browser:
        browser.post(
            "/accounts/register", json={"login": "route-requests", "password": "fixture password"}
        )
        signed = browser.post(
            "/accounts/session", json={"login": "route-requests", "password": "fixture password"}
        ).json()
        root = "/accounts/workspace"
        assert (
            browser.post(root + "/assistant/requests", json={"notice_id": "invalid"}).status_code
            == 403
        )
        browser.headers["X-CSRF-Token"] = signed["csrf"]
        browser.post(root + "/tasks", json={"title": "Owned reference", "due": "2000-01-01"})
        notice = browser.get(root + "/notifications").json()["items"][0]
        item = browser.post(root + "/assistant/requests", json={"notice_id": notice["id"]}).json()
        result = browser.post(
            root + "/assistant/chat",
            json={
                "message": "Add a task on 2026-11-09",
                "request_id": item["id"],
                "request_version": 1,
            },
        )
        assert result.status_code == 200, result.text
        proposal = result.json()["proposal"]
        reopened = browser.get(root + "/assistant/requests/" + item["id"]).json()
        assert reopened["resume_proposal"]["id"] == proposal["id"]
        assert reopened["resume_proposal"]["payload"]["title"] == "Confirmed fixture"
        tracked = AccountRequests(app.state.assistant.engine)
        assert tracked.result(signed["account_id"], item["id"], 2, None)
        assert tracked.get(signed["account_id"], item["id"])["proposal_id"] == proposal["id"]
        second = browser.post(
            root + "/assistant/chat",
            json={
                "message": "Add another task on 2026-11-09",
                "request_id": item["id"],
                "request_version": 3,
            },
        )
        assert second.status_code == 200, second.text
        assert second.json()["proposal"]["id"] != proposal["id"]
        assert result.json()["request_tracking_updated"]
        assert "Owned reference" in captured[0]["messages"][0]["content"]
        assert browser.get(root + "/assistant/history").json()["messages"] == []
        assert (
            browser.get(root + "/assistant/requests/" + item["id"]).json()["status"]
            == "waiting_approval"
        )
        confirmed = browser.post(root + "/assistant/confirm", json={"id": proposal["id"]})
        assert confirmed.status_code == 200, confirmed.text
        done = browser.get(root + "/assistant/requests/" + item["id"]).json()
        assert done["status"] == "done"
        assert len(browser.get(root + "/tasks").json()) == 2
        assert (
            browser.post(
                root + "/assistant/chat",
                json={
                    "message": "Again",
                    "request_id": item["id"],
                    "request_version": done["version"],
                },
            ).status_code
            == 409
        )
