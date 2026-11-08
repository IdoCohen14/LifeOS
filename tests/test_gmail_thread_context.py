import json

import httpx
from test_gmail import connect


def test_invalid_or_missing_provider_threads_do_not_group_equal_subjects(client, setup_app):
    service = connect(setup_app[0])
    invalid = [None, None, "", [], {}, 123, "invalid thread", "x" * 129]
    ids = [f"message-{i}" for i in range(len(invalid))]

    def handler(request):
        path = request.url.path
        if path.endswith("/profile"):
            return httpx.Response(
                200, json={"emailAddress": "fixture@example.test", "historyId": "100"}
            )
        if path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": id} for id in ids]})
        id = path.rsplit("/", 1)[-1]
        message = {
            "id": id,
            "internalDate": "1793232000000",
            "labelIds": ["INBOX", "UNREAD"],
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Same course fixture"},
                    {"name": "From", "value": "fixture@college.edu"},
                ]
            },
        }
        index = ids.index(id)
        if index:
            message["threadId"] = invalid[index]
        return httpx.Response(200, json=message)

    service.http = httpx.Client(transport=httpx.MockTransport(handler))
    assert client.post("/integrations/gmail/sync").status_code == 200
    rows = client.get("/integrations/gmail/messages").json()
    assert len(rows) == len(ids)
    assert all(row["thread_id"] == row["id"] and row["cached_thread_count"] == 1 for row in rows)
    assert len(client.get("/integrations/gmail/queue").json()) == len(ids)


def test_mail_thread_count_uses_only_relevant_cached_messages_without_merging_review(
    client, setup_app
):
    from lifeos.gmail_models import GmailMessage
    from sqlalchemy.orm import Session

    with Session(setup_app[0].state.assistant.engine) as db:
        for index, (id, thread, subject, unread) in enumerate(
            [
                ("one", "thread-a", "Course one", True),
                ("two", "thread-a", "Course two", False),
                ("ad", "thread-a", "Discount coupon", True),
                ("other", "thread-b", "Course other", True),
            ]
        ):
            db.add(
                GmailMessage(
                    id=id,
                    payload=json.dumps(
                        {
                            "id": id,
                            "thread_id": thread,
                            "subject": subject,
                            "sender": "Teacher <fixture@college.edu>",
                            "snippet": "Fixture",
                            "unread": unread,
                            "received_at": 1000 + index,
                            "source_url": "https://mail.google.com/mail/u/0/#inbox/" + id,
                        }
                    ),
                )
            )
        db.commit()
    messages = {row["id"]: row for row in client.get("/integrations/gmail/messages").json()}
    assert set(messages) == {"one", "two", "other"}
    assert (
        messages["one"]["cached_thread_count"] == 2 and messages["two"]["cached_thread_count"] == 2
    )
    assert messages["other"]["cached_thread_count"] == 1
    assert {row["id"] for row in client.get("/integrations/gmail/queue").json()} == {"one", "other"}
    assert {
        row["id"] for row in client.post("/integrations/gmail/review", json={"id": "one"}).json()
    } == {"other"}
    assert (
        next(
            row for row in client.get("/integrations/gmail/messages").json() if row["id"] == "one"
        )["cached_thread_count"]
        == 2
    )
