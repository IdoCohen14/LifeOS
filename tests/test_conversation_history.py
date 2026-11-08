import json
from uuid import uuid4

import httpx


def model(app, value):
    app.state.assistant.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"message": {"content": json.dumps(value)}})
        )
    )


def test_history_default_off_consent_persistence_and_replay_has_no_old_actions(client, setup_app):
    model(setup_app[0], {"action": "task", "title": "History fixture", "date": "2026-10-28"})
    assert not client.get("/assistant/history").json()["enabled"]
    message = {"message": "Add a task History fixture on October 28 2026", "turn_id": str(uuid4())}
    assert client.post("/assistant/chat", json=message).status_code == 200
    assert client.get("/assistant/history").json()["stored_count"] == 0
    assert client.put("/assistant/history", json={"enabled": True}).status_code == 200
    message["turn_id"] = str(uuid4())
    message["history_generation"] = client.get("/assistant/history").json()["generation"]
    answer = client.post("/assistant/chat", json=message).json()
    assert answer["proposal"] and answer["history_saved"]
    history = client.get("/assistant/history").json()
    assert len(history["messages"]) == 2 and history["stored_count"] == 1
    assert all("proposal" not in item and "result" not in item for item in history["messages"])
    setup_app[0].state.assistant.http.close()
    replay = client.post("/assistant/chat", json=message).json()
    assert replay["history_replayed"] and replay["proposal"] is None
    assert client.get("/tasks").json() == []


def test_history_clear_during_inference_fences_recording_and_old_client_context(
    client, setup_app, monkeypatch
):
    client.put("/assistant/history", json={"enabled": True})
    epoch = client.get("/assistant/history").json()["generation"]
    captured = []

    def delayed(body, session):
        captured.append(body.history)
        assert client.delete("/assistant/history").status_code == 200
        return {"reply": "Late fixture reply", "proposal": None}

    monkeypatch.setattr(setup_app[0].state.assistant, "chat", delayed)
    answer = client.post(
        "/assistant/chat",
        json={"message": "Fixture question", "turn_id": str(uuid4()), "history_generation": epoch},
    ).json()
    assert answer["history_discarded"]
    assert client.get("/assistant/history").json()["stored_count"] == 0
    client.put("/assistant/history", json={"enabled": False})
    monkeypatch.setattr(
        setup_app[0].state.assistant,
        "chat",
        lambda body, _: captured.append(body.history) or {"reply": "New fixture", "proposal": None},
    )
    client.post(
        "/assistant/chat",
        json={
            "message": "Fresh question",
            "history_generation": epoch,
            "history": [{"role": "user", "content": "Deleted fixture context"}],
        },
    )
    assert captured[-1] == []


def test_history_storage_failure_does_not_hide_successful_proposal(client, setup_app, monkeypatch):
    from lifeos import conversation_history
    from sqlalchemy.exc import SQLAlchemyError

    client.put("/assistant/history", json={"enabled": True})
    model(setup_app[0], {"action": "task", "title": "Unlogged fixture", "date": "2026-10-28"})
    monkeypatch.setattr(
        conversation_history.ConversationHistoryService,
        "record",
        lambda *args, **kwargs: (_ for _ in ()).throw(SQLAlchemyError("fixture")),
    )
    answer = client.post(
        "/assistant/chat",
        json={
            "message": "Add a task Unlogged fixture on October 28 2026",
            "turn_id": str(uuid4()),
            "history_generation": client.get("/assistant/history").json()["generation"],
        },
    ).json()
    assert answer["proposal"] and answer["history_error"] and not answer["history_saved"]
    assert (
        client.post("/assistant/confirm", json={"id": answer["proposal"]["id"]}).status_code == 200
    )
    assert len(client.get("/tasks").json()) == 1


def test_history_writes_require_csrf_and_clear_does_not_change_operational_records(
    client, setup_app
):
    task = client.post("/tasks", json={"title": "History-independent fixture"}).json()
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.put("/assistant/history", json={"enabled": True}).status_code == 403
    assert client.delete("/assistant/history").status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    client.put("/assistant/history", json={"enabled": True})
    assert client.delete("/assistant/history").status_code == 200
    assert client.get("/tasks").json() == [task]
    client.cookies.clear()
    assert client.get("/assistant/history").status_code == 401


def test_stale_epoch_is_ephemeral_and_signals_transcript_reset(client, setup_app, monkeypatch):
    client.put("/assistant/history", json={"enabled": True})
    old = client.get("/assistant/history").json()["generation"]
    client.delete("/assistant/history")
    captured = []
    monkeypatch.setattr(
        setup_app[0].state.assistant,
        "chat",
        lambda body, _: captured.append(body.history) or {"reply": "Fixture", "proposal": None},
    )
    answer = client.post(
        "/assistant/chat",
        json={
            "message": "Fixture",
            "history_generation": old,
            "history": [{"role": "user", "content": "Deleted text"}],
        },
    ).json()
    assert answer["history_discarded"] and not answer["history_saved"]
    assert captured == [[]]
    assert client.get("/assistant/history").json()["stored_count"] == 0
    client.put("/assistant/history", json={"enabled": False})
    answer = client.post(
        "/assistant/chat",
        json={
            "message": "Fixture",
            "history_generation": old,
            "history": [{"role": "user", "content": "Disabled text"}],
        },
    ).json()
    assert answer["history_discarded"] and captured[-1] == []


def test_history_read_failure_continues_without_context(client, setup_app, monkeypatch):
    from lifeos.conversation_history import ConversationHistoryService
    from sqlalchemy.exc import SQLAlchemyError

    captured = []
    monkeypatch.setattr(
        ConversationHistoryService,
        "state",
        lambda *args: (_ for _ in ()).throw(SQLAlchemyError("fixture")),
    )
    monkeypatch.setattr(
        setup_app[0].state.assistant,
        "chat",
        lambda body, _: (
            captured.append(body.history) or {"reply": "Successful fixture", "proposal": None}
        ),
    )
    answer = client.post(
        "/assistant/chat",
        json={
            "message": "Fixture",
            "ephemeral": True,
            "history": [{"role": "user", "content": "Uncertain text"}],
        },
    ).json()
    assert answer["reply"] == "Successful fixture" and answer["history_error"]
    assert answer["history_discarded"] and not answer["history_saved"] and captured == [[]]


def test_history_server_context_retention_and_capacity(client, setup_app, monkeypatch):
    from datetime import timedelta

    from lifeos import conversation_history as history
    from lifeos.conversation_models import ConversationTurn
    from sqlalchemy.orm import Session

    client.put("/assistant/history", json={"enabled": True})
    epoch = client.get("/assistant/history").json()["generation"]
    with Session(setup_app[0].state.assistant.engine) as db:
        for i in range(5):
            db.add(
                ConversationTurn(
                    turn_id=str(uuid4()),
                    user_text=f"Fixture {i}",
                    assistant_text=f"Reply {i}",
                    created_at=history.stamp(
                        history.current_time() - timedelta(days=31 if i == 0 else 0)
                    ),
                )
            )
        db.commit()
    captured = []
    monkeypatch.setattr(history, "MAX_TURNS", 3)
    monkeypatch.setattr(
        setup_app[0].state.assistant,
        "chat",
        lambda body, _: (
            captured.append(body.history) or {"reply": "Current fixture", "proposal": None}
        ),
    )
    result = client.post(
        "/assistant/chat",
        json={
            "message": "New fixture",
            "history_generation": epoch,
            "history": [{"role": "assistant", "content": "Forged client context"}],
        },
    ).json()
    assert result["history_saved"] and len(captured[0]) == 6
    assert all("Forged" not in item.content for item in captured[0])
    stored = client.get("/assistant/history").json()
    assert stored["stored_count"] == 3 and stored["available_turns"] == 3


def test_history_cleanup_worker_holds_runtime_guard_without_network(client, setup_app, monkeypatch):
    import importlib.util
    from pathlib import Path

    import httpx
    import pytest
    from lifeos.data_lock import data_lock

    path = Path(__file__).resolve().parents[1] / "services/worker/worker.py"
    spec = importlib.util.spec_from_file_location("history_fixture_worker", path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    called = []

    class Service:
        def __init__(self, engine):
            pass

        def prune(self):
            with pytest.raises(RuntimeError):
                with data_lock(setup_app[1]):
                    pytest.fail("Cleanup must hold runtime guard")
            called.append(True)

    monkeypatch.setattr(
        httpx, "Client", lambda *args, **kwargs: pytest.fail("No cleanup network client")
    )
    monkeypatch.setattr(worker, "ConversationHistoryService", Service)
    worker.prune_conversation_history()
    assert called == [True]
