import httpx
from test_moodle import ICS, URL


def test_observed_moodle_changes_follow_successful_snapshots_and_clear_on_disconnect(
    client, setup_app
):
    service = setup_app[0].state.moodle
    assert client.post("/integrations/moodle/config", json={"url": URL}).status_code == 200
    content = ICS
    service.http = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=content))
    )
    assert client.post("/integrations/moodle/sync").status_code == 200
    assert client.get("/integrations/moodle/changes").json() == []
    changed = ICS.replace(b"SUMMARY:Assignment", b"SUMMARY:Updated fixture")
    extra = (
        changed.split(b"BEGIN:VEVENT")[1]
        .split(b"END:VEVENT")[0]
        .replace(b"UID:deadline", b"UID:extra")
        .replace(b"SUMMARY:Updated fixture", b"SUMMARY:Added fixture")
    )
    content = changed.replace(
        b"END:VCALENDAR", b"BEGIN:VEVENT" + extra + b"END:VEVENT\r\nEND:VCALENDAR"
    )
    assert client.post("/integrations/moodle/sync").status_code == 200
    changes = client.get("/integrations/moodle/changes").json()
    assert {row["kind"] for row in changes} == {"added", "changed"}
    updated = next(row for row in changes if row["kind"] == "changed")
    assert (
        updated["previous"]["title"] == "Assignment"
        and updated["current"]["title"] == "Updated fixture"
    )
    assert "private-fixture" not in str(changes) and "authtoken" not in str(changes)
    assert client.post("/integrations/moodle/sync").status_code == 200
    assert client.get("/integrations/moodle/changes").json() == changes
    content = b"<html>Login required</html>"
    assert client.post("/integrations/moodle/sync").status_code == 502
    assert client.get("/integrations/moodle/changes").json() == changes
    content = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Fixture//EN\r\nEND:VCALENDAR\r\n"
    assert client.post("/integrations/moodle/sync").status_code == 200
    assert (
        sum(row["kind"] == "removed" for row in client.get("/integrations/moodle/changes").json())
        == 2
    )
    assert client.post("/integrations/moodle/disconnect").status_code == 200
    assert client.get("/integrations/moodle/changes").json() == []
