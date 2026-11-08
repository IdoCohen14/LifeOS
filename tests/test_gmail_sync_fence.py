import httpx
from test_gmail import connect


def test_sync_that_loses_ownership_cannot_replace_cache_or_new_owner_state(client, setup_app):
    from lifeos.gmail_models import GmailConnection
    from sqlalchemy.orm import Session

    service = connect(setup_app[0])
    replaced = [False]

    def handler(request):
        path = request.url.path
        if path.endswith("/profile"):
            return httpx.Response(
                200, json={"emailAddress": "fixture@example.test", "historyId": "100"}
            )
        if path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "a"}]})
        if path.endswith("/history"):
            return httpx.Response(404)
        if replaced[0]:
            with Session(service.engine) as db:
                row = db.get(GmailConnection, 1)
                row.lease_owner = "new-owner-fixture"
                row.lease_until = 9999999999
                row.history_id = "777"
                row.error = "new-owner-state"
                db.commit()
        return httpx.Response(
            200,
            json={
                "id": "a",
                "internalDate": "1793232000000",
                "labelIds": ["INBOX", "UNREAD"],
                "payload": {
                    "headers": [
                        {
                            "name": "Subject",
                            "value": "Course changed" if replaced[0] else "Course original",
                        },
                        {"name": "From", "value": "fixture@college.edu"},
                    ]
                },
            },
        )

    service.http = httpx.Client(transport=httpx.MockTransport(handler))
    assert client.post("/integrations/gmail/sync").status_code == 200
    before = client.get("/integrations/gmail/messages").json()
    replaced[0] = True
    assert client.post("/integrations/gmail/sync").status_code == 409
    assert client.get("/integrations/gmail/messages").json() == before
    with Session(service.engine) as db:
        row = db.get(GmailConnection, 1)
        assert row.lease_owner == "new-owner-fixture"
        assert row.lease_until == 9999999999
        assert row.history_id == "777"
        assert row.error == "new-owner-state"
