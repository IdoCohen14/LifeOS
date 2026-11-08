import httpx
from test_gmail import connect


def test_gmail_incremental_refresh_reuses_unchanged_metadata_and_keeps_latest_membership(
    client, setup_app
):
    service = connect(setup_app[0])
    phase = [1]
    fetched = []

    def handler(request):
        path = request.url.path
        if path.endswith("/profile"):
            return httpx.Response(
                200, json={"emailAddress": "fixture@example.test", "historyId": str(phase[0] * 100)}
            )
        if path.endswith("/messages"):
            return httpx.Response(
                200,
                json={
                    "messages": [{"id": id} for id in (["a", "b"] if phase[0] < 3 else ["b", "c"])]
                },
            )
        if path.endswith("/history"):
            assert request.url.params["startHistoryId"] == str((phase[0] - 1) * 100)
            return httpx.Response(
                200,
                json={
                    "historyId": str(phase[0] * 100),
                    "history": [{"labelsRemoved": [{"message": {"id": "b"}}]}]
                    if phase[0] == 2
                    else [{"messagesAdded": [{"message": {"id": "c"}}]}]
                    if phase[0] == 3
                    else [],
                },
            )
        id = path.rsplit("/", 1)[-1]
        fetched.append(id)
        if phase[0] == 2:
            # Interleave local review after sync captured its cache, before replacement.
            service.review(id="a")
        return httpx.Response(
            200,
            json={
                "id": id,
                "threadId": "actual-thread",
                "internalDate": "1793232000000",
                "labelIds": ["INBOX"] + (["UNREAD"] if id != "b" or phase[0] == 1 else []),
                "snippet": "Course fixture",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Course " + id},
                        {"name": "From", "value": "fixture@college.edu"},
                    ]
                },
            },
        )

    service.http = httpx.Client(transport=httpx.MockTransport(handler))
    assert client.post("/integrations/gmail/sync").status_code == 200
    assert fetched == ["a", "b"]
    rows = client.get("/integrations/gmail/messages").json()
    assert all(row["thread_id"] == "actual-thread" for row in rows)
    assert all(row["cached_thread_count"] == 2 for row in rows)
    phase[0] = 2
    fetched.clear()
    assert client.post("/integrations/gmail/sync").status_code == 200
    assert fetched == ["b"]
    assert all(row["id"] != "a" for row in client.get("/integrations/gmail/queue").json())
    assert any(row["id"] == "a" for row in client.get("/integrations/gmail/messages").json())
    assert (
        next(row for row in client.get("/integrations/gmail/messages").json() if row["id"] == "b")[
            "unread"
        ]
        is False
    )
    phase[0] = 3
    fetched.clear()
    assert client.post("/integrations/gmail/sync").status_code == 200
    assert fetched == ["c"]
    assert {row["id"] for row in client.get("/integrations/gmail/messages").json()} == {"b", "c"}

    # A pre-thread-context cache must be enriched once, even with no history changes.
    import json

    from lifeos.gmail_models import GmailMessage
    from sqlalchemy.orm import Session

    with Session(service.engine) as db:
        row = db.get(GmailMessage, "b")
        payload = json.loads(row.payload)
        payload.pop("thread_id")
        row.payload = json.dumps(payload)
        db.commit()
    phase[0] = 4
    fetched.clear()
    assert client.post("/integrations/gmail/sync").status_code == 200
    assert fetched == ["b"]
    assert all(
        row["cached_thread_count"] == 2 for row in client.get("/integrations/gmail/messages").json()
    )
    phase[0] = 5
    fetched.clear()
    assert client.post("/integrations/gmail/sync").status_code == 200
    assert fetched == []


def test_gmail_expired_history_fallback_preserves_checkpoint_on_failure(client, setup_app):
    from lifeos.gmail_models import GmailConnection
    from sqlalchemy.orm import Session

    service = connect(setup_app[0])
    phase = [1]
    fail = [False]
    fetched = []

    def handler(request):
        path = request.url.path
        if path.endswith("/profile"):
            return httpx.Response(
                200, json={"emailAddress": "fixture@example.test", "historyId": str(phase[0] * 100)}
            )
        if path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "a"}]})
        if path.endswith("/history"):
            if fail[0] == "malformed":
                return httpx.Response(
                    200, json={"historyId": "200", "history": [{"messagesAdded": [None]}]}
                )
            return httpx.Response(404)
        fetched.append("a")
        if fail[0]:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "id": "a",
                "internalDate": "1793232000000",
                "labelIds": ["INBOX", "UNREAD"],
                "snippet": "Course fixture",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Course fixture"},
                        {"name": "From", "value": "fixture@college.edu"},
                    ]
                },
            },
        )

    service.http = httpx.Client(transport=httpx.MockTransport(handler))
    assert client.post("/integrations/gmail/sync").status_code == 200
    old = client.get("/integrations/gmail/messages").json()
    phase[0] = 2
    fail[0] = True
    assert client.post("/integrations/gmail/sync").status_code == 502
    assert client.get("/integrations/gmail/messages").json() == old
    with Session(service.engine) as db:
        assert db.get(GmailConnection, 1).history_id == "100"
    fail[0] = "malformed"
    fetched.clear()
    assert client.post("/integrations/gmail/sync").status_code == 502
    assert fetched == []
    assert client.get("/integrations/gmail/messages").json() == old
    with Session(service.engine) as db:
        assert db.get(GmailConnection, 1).history_id == "100"
        assert db.get(GmailConnection, 1).error == "invalid_provider_response"
    fail[0] = False
    fetched.clear()
    assert client.post("/integrations/gmail/sync").status_code == 200
    assert fetched == ["a"]
    with Session(service.engine) as db:
        assert db.get(GmailConnection, 1).history_id == "200"
    assert client.post("/integrations/gmail/disconnect").status_code == 200
    with Session(service.engine) as db:
        assert db.get(GmailConnection, 1).history_id is None
