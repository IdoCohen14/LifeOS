def test_builtin_help_is_authenticated_constant_and_does_not_infer_or_write(
    client, setup_app, monkeypatch
):
    import pytest

    monkeypatch.setattr(
        setup_app[0].state.assistant,
        "infer",
        lambda *args: pytest.fail("No help catalog inference"),
    )
    before = client.get("/tasks").json(), client.get("/events").json()
    response = client.get("/assistant/help")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "built_in"
    ids = {topic["id"] for topic in body["topics"]}
    assert {
        "planning",
        "backups",
        "recurrence",
        "push",
        "history",
        "weekly_review",
        "academic_courses",
        "academic_timetable",
        "academic_deadlines",
    } <= ids
    assert all(len(topic["label"]) == 2 and len(topic["answer"]) == 2 for topic in body["topics"])
    assert before == (client.get("/tasks").json(), client.get("/events").json())
    assert response.headers["cache-control"] == "no-store"
    client.cookies.clear()
    assert client.get("/assistant/help").status_code == 401


def test_help_catalog_and_model_topic_allowlist_match(client):
    from typing import get_args

    from lifeos.assistant import Intent

    ids = {topic["id"] for topic in client.get("/assistant/help").json()["topics"]}
    assert ids == set(get_args(Intent.model_fields["topic"].annotation))


def test_new_allowlisted_help_topic_uses_shared_current_instructions_without_proposal(
    client, setup_app, monkeypatch
):
    import json

    import httpx
    from lifeos.assistant_help import HELP

    monkeypatch.setattr(
        setup_app[0].state.assistant,
        "infer",
        lambda body: httpx.Response(
            200, json={"message": {"content": json.dumps({"action": "help", "topic": "backups"})}}
        ),
    )
    response = client.post(
        "/assistant/chat", json={"message": "How do I inspect my encrypted backup?"}
    )
    assert response.status_code == 200
    assert response.json()["reply"] == HELP["backups"][0]
    assert response.json()["proposal"] is None
    assert client.get("/tasks").json() == [] and client.get("/events").json() == []
