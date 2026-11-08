import json


def test_mail_notifications_opt_in_and_mail_read_state_are_separate(client, setup_app):
    from lifeos.gmail_models import GmailConnection, GmailMessage, GmailReviewed
    from sqlalchemy.orm import Session

    engine = setup_app[0].state.assistant.engine

    def message(id, subject, unread=True):
        return GmailMessage(
            id=id,
            payload=json.dumps(
                {
                    "id": id,
                    "subject": subject,
                    "sender": "Teacher <fixture@college.edu>",
                    "snippet": "Fixture text",
                    "unread": unread,
                    "received_at": 1000,
                    "source_url": f"https://mail.google.com/mail/u/0/#inbox/{id}",
                }
            ),
        )

    with Session(engine) as db:
        db.add(GmailConnection(id=1, state="connected", last_success=1000))
        db.add_all(
            [
                message("new", "Assignment fixture"),
                message("read", "Exam fixture", False),
                message("ad", "Discount coupon fixture"),
                message("reviewed", "Course fixture"),
            ]
        )
        db.add(GmailReviewed(id="reviewed"))
        db.commit()
    assert not any(
        item["kind"] == "new_mail" for item in client.get("/notifications").json()["items"]
    )
    feed = client.put("/notifications/preferences", json={"mail": True}).json()
    items = [item for item in feed["items"] if item["kind"] == "new_mail"]
    assert len(items) == 1 and items[0]["source_ids"] == ["new"]
    id = items[0]["id"]
    assert client.post("/notifications/read", json={"ids": [id]}).status_code == 200
    assert any(message["id"] == "new" for message in client.get("/integrations/gmail/queue").json())
    assert (
        client.put("/notifications/preferences", json={"tasks": False}).json()["preferences"][
            "mail"
        ]
        is True
    )
    assert client.post("/integrations/gmail/review", json={"id": "new"}).status_code == 200
    assert not any(
        item["kind"] == "new_mail" for item in client.get("/notifications").json()["items"]
    )
    # Undo restores the same notice identity; a later message stays independent.
    assert (
        client.post("/integrations/gmail/review", json={"id": "new", "undo": True}).status_code
        == 200
    )
    restored = [
        item for item in client.get("/notifications").json()["items"] if item["kind"] == "new_mail"
    ]
    assert len(restored) == 1 and restored[0]["id"] == id
    with Session(engine) as db:
        original = db.get(GmailMessage, "new").payload
        db.add(message("later", "Course later fixture"))
        db.commit()
    assert client.post("/integrations/gmail/review", json={"id": "new"}).status_code == 200
    remaining = [
        item for item in client.get("/notifications").json()["items"] if item["kind"] == "new_mail"
    ]
    assert len(remaining) == 1 and remaining[0]["source_ids"] == ["later"]
    assert client.post("/integrations/gmail/review", json={"all": True}).json() == []
    assert not any(
        item["kind"] == "new_mail" for item in client.get("/notifications").json()["items"]
    )
    with Session(engine) as db:
        assert db.get(GmailMessage, "new").payload == original
        assert json.loads(db.get(GmailMessage, "later").payload)["unread"] is True
