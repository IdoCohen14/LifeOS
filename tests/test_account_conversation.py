from lifeos.account_conversation import AccountConversation
from lifeos.account_preferences import AccountPreferences
from lifeos.accounts import AccountService


def test_account_history_is_opt_in_private_resettable_and_kept_when_disabled(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    a = accounts.register("history-a", "fixture password a")
    b = accounts.register("history-b", "fixture password b")
    prefs = AccountPreferences(engine)
    history = AccountConversation(engine)
    assert history.append(a, "Question fixture", "Answer fixture") is False
    prefs.put(a, "history", {"enabled": True}, 0)
    assert history.append(a, "Question fixture", "Answer fixture") is True
    assert history.list(b) == []
    assert len(history.list(a, context_only=True)) == 1
    history.clear(a, context_only=True)
    assert len(history.list(a)) == 1 and history.list(a, context_only=True) == []
    history.append(a, "New fixture", "New answer fixture")
    assert len(history.list(a, context_only=True)) == 1
    prefs.put(a, "history", {"enabled": False}, 1)
    assert history.append(a, "Not saved fixture", "Not saved fixture") is False
    assert history.list(a, context_only=True) == [] and len(history.list(a)) == 2
    prefs.put(b, "history", {"enabled": True}, 0)
    history.append(b, "Other fixture", "Other answer fixture")
    history.clear(a)
    assert history.list(a) == [] and len(history.list(b)) == 1


def test_account_chat_history_replay_and_reset_fence_late_model_results(client, setup_app):
    from uuid import uuid4

    from lifeos.assistant import ChatInput
    from lifeos.security import token_hash

    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owner = auth.register("history-chat", "fixture password")
    session = token_hash(auth.login("history-chat", "fixture password")["token"])
    prefs = AccountPreferences(engine)
    prefs.put(owner, "history", {"enabled": True}, 0)
    history = AccountConversation(engine)
    calls = []

    class Model:
        def chat(self, body, session_hash):
            calls.append(body)
            if body.message == "reset during response":
                history.clear(owner, context_only=True)
            return {"reply": "Fixture reply", "proposal": None}

    state = history.history(owner)
    body = ChatInput(
        message="fixture question", turn_id=str(uuid4()), history_generation=state["generation"]
    )
    result = history.chat(owner, Model(), body, session)
    assert result["history_saved"]
    replay = history.chat(owner, Model(), body, session)
    assert replay["history_replayed"] and len(calls) == 1
    late = history.chat(
        owner,
        Model(),
        ChatInput(
            message="reset during response",
            turn_id=str(uuid4()),
            history_generation=state["generation"],
        ),
        session,
    )
    assert not late["history_saved"] and late["history_discarded"]
    assert len(history.list(owner)) == 1 and history.list(owner, context_only=True) == []
