"""Deterministic two-client acceptance with the real inference and write locks."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier, Event

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = "/accounts/workspace"


@contextmanager
def browsers(setup_app, monkeypatch):
    monkeypatch.setenv("LIFEOS_ACCOUNT_MODE", "1")
    app = setup_app[2]()
    entered, release = Event(), Event()

    def model(request):
        assert request.url.path == "/api/chat"
        entered.set()
        if not release.wait(10):
            raise AssertionError("Fixture model was not released")
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "action": "task",
                            "title": "Late fixture task",
                            "date": "2026-11-09",
                        }
                    )
                }
            },
        )

    app.state.assistant.http.close()
    app.state.assistant.http = httpx.Client(transport=httpx.MockTransport(model))
    headers = {"X-LifeOS-Key": "test-process-key"}
    try:
        with (
            TestClient(app, base_url="http://127.0.0.1:8000", headers=headers) as first,
            TestClient(app, base_url="http://127.0.0.1:8000", headers=headers) as second,
        ):
            assert (
                first.post(
                    "/accounts/register",
                    json={"login": "concurrency-fixture", "password": "fixture password"},
                ).status_code
                == 201
            )
            signed = first.post(
                "/accounts/session",
                json={"login": "concurrency-fixture", "password": "fixture password"},
            ).json()
            for client in (first, second):
                client.headers["X-CSRF-Token"] = signed["csrf"]
            second.cookies.update(first.cookies)
            assert (
                first.post(
                    ROOT + "/tasks", json={"title": "Source fixture", "due": "2000-01-01"}
                ).status_code
                == 201
            )
            notice = first.get(ROOT + "/notifications").json()["items"][0]
            tracked = first.post(
                ROOT + "/assistant/requests", json={"notice_id": notice["id"]}
            ).json()
            yield first, second, tracked, entered, release
    finally:
        release.set()
        app.state.assistant.http.close()


def message(tracked):
    return {
        "message": "Add a task on 2026-11-09",
        "request_id": tracked["id"],
        "request_version": tracked["version"],
    }


@pytest.mark.parametrize("choice", ["done", "waiting_source", "delete"])
def test_late_answer_preserves_other_tab_request_choice(setup_app, monkeypatch, choice):
    with (
        browsers(setup_app, monkeypatch) as (first, second, tracked, entered, release),
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        future = pool.submit(first.post, ROOT + "/assistant/chat", json=message(tracked))
        try:
            assert entered.wait(5)
            path = ROOT + "/assistant/requests/" + tracked["id"]
            if choice == "delete":
                changed = second.request("DELETE", path, json={"version": 1})
                assert changed.status_code == 204
            else:
                changed = second.patch(path, json={"version": 1, "status": choice})
                assert changed.status_code == 200
        finally:
            release.set()
        reply = future.result(10)
        assert reply.status_code == 200, reply.text
        assert reply.json()["proposal"] is not None
        assert reply.json()["request_tracking_updated"] is False
        current = second.get(path)
        if choice == "delete":
            assert current.status_code == 404
        else:
            assert current.json()["status"] == choice and current.json()["version"] == 2
        assert len(second.get(ROOT + "/tasks").json()) == 1


def test_second_tab_observes_actual_model_busy_without_duplicate_work(setup_app, monkeypatch):
    with (
        browsers(setup_app, monkeypatch) as (first, second, tracked, entered, release),
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        future = pool.submit(first.post, ROOT + "/assistant/chat", json=message(tracked))
        try:
            assert entered.wait(5)
            rejected = second.post(ROOT + "/assistant/chat", json=message(tracked))
            assert rejected.status_code == 429, rejected.text
            assert rejected.json()["detail"] == "assistant_busy"
        finally:
            release.set()
        assert future.result(10).status_code == 200
        assert len(second.get(ROOT + "/tasks").json()) == 1
        assert second.get(ROOT + "/assistant/requests/" + tracked["id"]).json()["version"] == 2


def test_two_confirmations_create_one_record_and_finish_tracking_once(setup_app, monkeypatch):
    with browsers(setup_app, monkeypatch) as (first, second, tracked, _, release):
        release.set()
        proposal = first.post(ROOT + "/assistant/chat", json=message(tracked)).json()["proposal"]
        barrier = Barrier(2)

        def confirm(client):
            barrier.wait(timeout=5)
            return client.post(ROOT + "/assistant/confirm", json={"id": proposal["id"]})

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(confirm, (first, second)))
        assert all(response.status_code == 200 for response in responses), [
            r.text for r in responses
        ]
        assert responses[0].json()["id"] == responses[1].json()["id"]
        assert len(first.get(ROOT + "/tasks").json()) == 2
        current = first.get(ROOT + "/assistant/requests/" + tracked["id"]).json()
        assert current["status"] == "done" and current["version"] == 3


def test_logout_during_inference_prevents_late_proposal_write(setup_app, monkeypatch):
    from lifeos.assistant_models import AssistantProposal
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    with (
        browsers(setup_app, monkeypatch) as (first, second, tracked, entered, release),
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        future = pool.submit(first.post, ROOT + "/assistant/chat", json=message(tracked))
        try:
            assert entered.wait(5)
            assert second.delete("/accounts/session").status_code == 204
        finally:
            release.set()
        assert future.result(10).status_code == 401
        with Session(setup_app[0].state.assistant.engine) as db:
            assert db.scalar(select(func.count()).select_from(AssistantProposal)) == 0
        signed = second.post(
            "/accounts/session",
            json={"login": "concurrency-fixture", "password": "fixture password"},
        ).json()
        second.headers["X-CSRF-Token"] = signed["csrf"]
        assert len(second.get(ROOT + "/tasks").json()) == 1
        assert second.get(ROOT + "/assistant/requests/" + tracked["id"]).json()["version"] == 1


def test_clear_history_during_inference_discards_late_transcript(setup_app, monkeypatch):
    with (
        browsers(setup_app, monkeypatch) as (first, second, tracked, entered, release),
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        enabled = first.put(ROOT + "/assistant/history", json={"enabled": True})
        assert enabled.status_code == 200
        body = {**message(tracked), "history_generation": enabled.json()["generation"]}
        future = pool.submit(first.post, ROOT + "/assistant/chat", json=body)
        try:
            assert entered.wait(5)
            assert second.delete(ROOT + "/assistant/history").status_code == 200
        finally:
            release.set()
        response = future.result(10)
        assert response.status_code == 200, response.text
        assert response.json()["history_discarded"] and not response.json()["history_saved"]
        assert second.get(ROOT + "/assistant/history").json()["messages"] == []
        assert len(second.get(ROOT + "/tasks").json()) == 1
