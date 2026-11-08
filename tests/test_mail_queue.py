import json

from sqlalchemy.orm import Session


def test_daily_mail_queue_persists_review_without_changing_gmail(client, setup_app):
    from lifeos.gmail_models import GmailMessage

    service = setup_app[0].state.gmail
    with Session(service.engine) as db:
        for id, unread in [("first", True), ("second", True), ("old", False)]:
            db.add(
                GmailMessage(
                    id=id,
                    payload=json.dumps(
                        {"id": id, "subject": "Job interview", "unread": unread, "received_at": 1}
                    ),
                )
            )
        db.commit()
    assert len(client.get("/integrations/gmail/queue").json()) == 2
    assert client.post("/integrations/gmail/review", json={"id": "first"}).status_code == 200
    assert [m["id"] for m in client.get("/integrations/gmail/queue").json()] == ["second"]
    restored = client.post("/integrations/gmail/review", json={"id": "first", "undo": True})
    assert restored.status_code == 200 and restored.json()[0]["id"] == "first"
    assert client.post("/integrations/gmail/review", json={"id": "first"}).status_code == 200
    assert len(service.messages()) == 3
    with Session(service.engine) as db:
        db.delete(db.get(GmailMessage, "first"))
        db.commit()
        db.add(
            GmailMessage(
                id="first",
                payload=json.dumps(
                    {"id": "first", "subject": "Job interview", "unread": True, "received_at": 1}
                ),
            )
        )
        db.commit()
    assert len(client.get("/integrations/gmail/queue").json()) == 1
    assert client.post("/integrations/gmail/review", json={"all": True}).json() == []
    assert client.get("/integrations/gmail/queue").json() == []
    client.headers["X-CSRF-Token"] = "bad"
    assert client.post("/integrations/gmail/review", json={"all": True}).status_code == 403
