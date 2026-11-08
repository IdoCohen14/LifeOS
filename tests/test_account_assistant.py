import json

import httpx
import pytest
from fastapi import HTTPException
from lifeos.account_records import AccountRecords
from lifeos.accounts import AccountService
from lifeos.assistant import AssistantService, ChatInput
from lifeos.security import token_hash


def test_account_assistant_scopes_schedule_proposals_and_confirmation(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("assistant-a", "fixture password a")
    b = auth.register("assistant-b", "fixture password b")
    sessions = [
        auth.login("assistant-a", "fixture password a"),
        auth.login("assistant-b", "fixture password b"),
    ]
    hashes = [token_hash(row["token"]) for row in sessions]
    store = AccountRecords(engine)
    store.save(a, "tasks", {"title": "A only", "due": "2026-11-02"})
    store.save(b, "tasks", {"title": "B only", "due": "2026-11-02"})
    service = AssistantService(engine, None, None, account_id=a)
    intent = {"action": "schedule", "date": "2026-11-02"}
    service.http.close()
    service.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"message": {"content": json.dumps(intent)}})
        )
    )
    try:
        reply = service.chat(ChatInput(message="What is planned on 2026-11-02?"), hashes[0])
        assert [row["title"] for row in reply["schedule"]["tasks"]] == ["A only"]
        with pytest.raises(HTTPException):
            service.chat(ChatInput(message="My schedule"), hashes[1])
        intent.update(action="task", title="Proposed")
        proposal = service.chat(ChatInput(message="Add a task on 2026-11-02"), hashes[0])[
            "proposal"
        ]
        assert len(store.list(a, "tasks")) == 1
        with pytest.raises(HTTPException):
            service.confirm(proposal["id"], hashes[1])
        result = service.confirm(proposal["id"], hashes[0])
        assert service.confirm(proposal["id"], hashes[0]) == result
        assert len(store.list(a, "tasks")) == 2 and len(store.list(b, "tasks")) == 1
        auth.logout(sessions[0]["token"])
        with pytest.raises(HTTPException):
            service.confirm(proposal["id"], hashes[0])
    finally:
        service.http.close()
