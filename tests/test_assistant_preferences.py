import json
from datetime import datetime, timezone

import httpx
import pytest


def preferences(client, **changes):
    value = client.get("/planning/preferences").json()
    response = client.put(
        "/planning/preferences",
        json={
            **value,
            "enabled": False,
            "assistant_enabled": True,
            "duration": 90,
            "window_start": "09:30",
            "window_end": "17:00",
            "days": 7,
            **changes,
        },
    )
    assert response.status_code == 200
    return response.json()


def configured(setup_app, monkeypatch, duration=60, day="2026-10-28"):
    from lifeos import assistant

    monkeypatch.setattr(
        assistant, "current_time", lambda: datetime(2026, 10, 27, 6, tzinfo=timezone.utc)
    )
    prompts = []

    def inferred(request):
        prompts.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "action": "find_slot",
                            "title": "Verified preference fixture",
                            "date": day,
                            "duration": duration,
                        }
                    )
                }
            },
        )

    setup_app[0].state.assistant.http = httpx.Client(transport=httpx.MockTransport(inferred))
    return prompts


def ask(client, message="Find time tomorrow"):
    return client.post("/assistant/chat", json={"message": message})


@pytest.mark.parametrize("explicit", [False, True])
def test_assistant_uses_verified_window_and_only_defaults_missing_duration(
    client, setup_app, monkeypatch, explicit
):
    saved = preferences(client)
    prompts = configured(setup_app, monkeypatch, 30 if explicit else 60)
    response = ask(client, "Find 30 minutes free tomorrow" if explicit else "Find time tomorrow")
    assert response.status_code == 200
    result = response.json()
    record = result["proposal"]["payload"]
    assert record["start"] == "2026-10-28T07:30:00Z"
    assert (
        datetime.fromisoformat(record["end"].replace("Z", "+00:00"))
        - datetime.fromisoformat(record["start"].replace("Z", "+00:00"))
    ).total_seconds() == (30 if explicit else 90) * 60
    assert result["proposal"]["preference_source"] == {
        "weekdays": list(range(1, 8)),
        "window_start": "09:30",
        "window_end": "17:00",
        "default_duration": None if explicit else 90,
    }
    assert "09:30" not in result["reply"] and "17:00" not in result["reply"]
    assert "09:30" not in json.dumps(prompts) and "17:00" not in json.dumps(prompts)
    assert not saved["enabled"] and saved["assistant_enabled"]
    assert client.get("/events").json() == []
    assert (
        client.post("/assistant/confirm", json={"id": result["proposal"]["id"]}).status_code == 200
    )


def test_assistant_preference_metadata_does_not_enter_saved_history_context(
    client, setup_app, monkeypatch
):
    preferences(client)
    prompts = configured(setup_app, monkeypatch)
    state = client.put("/assistant/history", json={"enabled": True}).json()
    for _ in range(2):
        response = client.post(
            "/assistant/chat",
            json={"message": "Find time tomorrow", "history_generation": state["generation"]},
        )
        assert response.status_code == 200 and response.json()["history_saved"]
    assert len(prompts[1]["messages"]) >= 4
    serialized = json.dumps(prompts)
    assert (
        "09:30" not in serialized
        and "17:00" not in serialized
        and "2026-10-28T07:30" not in serialized
    )


def test_assistant_preference_postflush_revision_change_rolls_back_and_retries(
    client, setup_app, monkeypatch
):
    from lifeos.assistant_models import AssistantProposal
    from lifeos.planning_preferences import PlanningPreferences
    from sqlalchemy import event, update
    from sqlalchemy.orm import Session

    saved = preferences(client)
    configured(setup_app, monkeypatch)
    proposal = ask(client).json()["proposal"]
    engine = setup_app[0].state.assistant.engine
    flushed = []

    def changed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO events"):
            flushed.append(True)
            connection.execute(
                update(PlanningPreferences).values(
                    assistant_enabled=False, revision=saved["revision"] + 1
                )
            )

    event.listen(engine, "after_cursor_execute", changed)
    try:
        assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 409
    finally:
        event.remove(engine, "after_cursor_execute", changed)
    assert flushed and client.get("/events").json() == []
    with Session(engine) as db:
        row = db.get(PlanningPreferences, 1)
        assert row.assistant_enabled and row.revision == saved["revision"]
        assert db.get(AssistantProposal, proposal["id"]).confirmed_id is None
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 200
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 200
    assert len(client.get("/events").json()) == 1


def test_assistant_saved_window_skips_ambiguous_slots_and_keeps_requested_date(
    client, setup_app, monkeypatch
):
    from lifeos import assistant

    preferences(client, duration=60, window_start="00:00", window_end="04:00")
    configured(setup_app, monkeypatch, day="2026-10-25")
    monkeypatch.setattr(
        assistant, "current_time", lambda: datetime(2026, 10, 24, 6, tzinfo=timezone.utc)
    )
    client.post(
        "/events",
        json={
            "title": "DST fixture",
            "start": "2026-10-25T00:00:00+03:00",
            "end": "2026-10-25T01:00:00+03:00",
        },
    )
    proposal = ask(client, "Find 60 minutes free on 2026-10-25").json()["proposal"]
    assert proposal["payload"]["start"] == "2026-10-25T00:00:00Z"
    current = client.get("/planning/preferences").json()
    assert (
        client.put("/planning/preferences", json={**current, "window_start": "01:30"}).status_code
        == 200
    )
    assert ask(client, "Find 60 minutes free on 2026-10-25").json()["proposal"] is None


def test_assistant_does_not_search_unrequested_later_days_or_leak_no_slot_window(
    client, setup_app, monkeypatch
):
    preferences(client)
    prompts = configured(setup_app, monkeypatch)
    client.post(
        "/events",
        json={
            "title": "Busy date fixture",
            "start": "2026-10-28",
            "end": "2026-10-29",
            "all_day": True,
        },
    )
    response = ask(client)
    assert response.status_code == 200 and response.json()["proposal"] is None
    assert "09:30" not in response.json()["reply"] and "17:00" not in response.json()["reply"]
    assert "09:30" not in json.dumps(prompts)


def test_assistant_preference_migration_keeps_existing_values_and_defaults_new_consent_off(
    client, setup_app, monkeypatch
):
    from alembic import command
    from alembic.config import Config
    from lifeos.db import ROOT, migrate

    saved = preferences(client, enabled=True)
    event = client.post(
        "/events",
        json={
            "title": "Migration fixture",
            "start": "2026-10-28",
            "end": "2026-10-29",
            "all_day": True,
        },
    ).json()
    engine = setup_app[0].state.assistant.engine
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "services/api/alembic"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, "0020")
    migrate(engine)
    assert client.get("/planning/preferences").json() == {**saved, "assistant_enabled": False}
    assert client.get("/events").json() == [event]


def test_assistant_opt_in_is_independent_and_default_off(client, setup_app, monkeypatch):
    assert client.get("/planning/preferences").json().get("assistant_enabled") is False
    preferences(client, enabled=True, assistant_enabled=False)
    configured(setup_app, monkeypatch)
    assert ask(client).json()["proposal"] is None
    record = ask(client, "Find 60 minutes free tomorrow").json()["proposal"]["payload"]
    assert record["start"] == "2026-10-28T06:00:00Z"


def test_old_client_appended_preference_proposal_is_not_forwarded_to_model(
    client, setup_app, monkeypatch
):
    preferences(client)
    prompts = configured(setup_app, monkeypatch)
    proposal = ask(client).json()["proposal"]
    response = client.post(
        "/assistant/chat",
        json={
            "message": "Find time tomorrow",
            "history": [
                {
                    "role": "assistant",
                    "content": "Review the details and confirm to save. "
                    + json.dumps(proposal["payload"]),
                }
            ],
        },
    )
    assert response.status_code == 200
    assert "2026-10-28T07:30" not in json.dumps(prompts[1]["messages"])


@pytest.mark.parametrize("change", ["duration", "disable", "reset"])
def test_assistant_preference_change_requires_fresh_review(client, setup_app, monkeypatch, change):
    saved = preferences(client)
    configured(setup_app, monkeypatch)
    proposal = ask(client).json()["proposal"]
    if change == "reset":
        assert (
            client.request(
                "DELETE", "/planning/preferences", json={"revision": saved["revision"]}
            ).status_code
            == 200
        )
    else:
        values = {
            **saved,
            **({"duration": 60} if change == "duration" else {"assistant_enabled": False}),
        }
        assert client.put("/planning/preferences", json=values).status_code == 200
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 409
    assert client.get("/events").json() == []


def test_assistant_selected_weekdays_do_not_switch_requested_date_or_enter_context(
    client, setup_app, monkeypatch
):
    preferences(client, weekdays=[1, 3])
    prompts = configured(setup_app, monkeypatch, day="2026-10-27")
    excluded = ask(client, "Find time today")
    assert excluded.status_code == 200 and excluded.json()["proposal"] is None
    assert "saved" in excluded.json()["reply"].lower() or "העדפות" in excluded.json()["reply"]
    assert client.get("/events").json() == []
    prompts = configured(setup_app, monkeypatch, day="2026-10-28")
    allowed = ask(client).json()["proposal"]
    assert allowed["preference_source"]["weekdays"] == [1, 3]
    contents = "\n".join(message["content"] for prompt in prompts for message in prompt["messages"])
    assert '"weekdays"' not in contents
    value = client.get("/planning/preferences").json()
    assert client.put("/planning/preferences", json={**value, "weekdays": [1]}).status_code == 200
    assert client.post("/assistant/confirm", json={"id": allowed["id"]}).status_code == 409
    assert client.get("/events").json() == []
