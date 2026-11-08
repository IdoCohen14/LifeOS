import httpx
import pytest
from lifeos.account_calendar import AccountCalendar
from lifeos.accounts import AccountService
from lifeos.google_calendar import GoogleCalendarService, GoogleProblem


def test_owned_calendar_selection_preserves_selected_cache_and_fences_old_sync(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owner = auth.register("selection-a", "fixture password")
    store = AccountCalendar(engine, setup_app[1])
    store.configure(owner, "google", {"refresh_token": "fixture"})
    lease = store.begin_sync(owner, "google")
    store.commit_sync(
        owner,
        "google",
        lease["owner"],
        lease["revision"],
        [
            {
                "id": "meta-a",
                "kind": "calendar",
                "calendar_id": "a",
                "name": "A",
                "selected": True,
                "token": "private-token",
            },
            {"id": "meta-b", "kind": "calendar", "calendar_id": "b", "name": "B", "selected": True},
            {"id": "visible-a", "kind": "visible", "calendar_id": "a", "payload": {"id": "a"}},
            {"id": "visible-b", "kind": "visible", "calendar_id": "b", "payload": {"id": "b"}},
        ],
    )
    old = store.begin_sync(owner, "google")
    selected = store.select(owner, ["b"])
    assert [row["id"] for row in selected if row["selected"]] == ["b"]
    assert "private-token" not in str(selected)
    assert store.events(owner) == [{"id": "b"}]
    with pytest.raises(RuntimeError):
        store.commit_sync(owner, "google", old["owner"], old["revision"], [])
    with pytest.raises(ValueError):
        store.select(owner, ["unknown"])


def test_account_calendar_delta_recurrence_expiry_and_failure_remain_isolated(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    a = accounts.register("calendar-a", "fixture password a")
    b = accounts.register("calendar-b", "fixture password b")
    store = AccountCalendar(engine, setup_app[1])
    phase = [1]
    tokens = []

    def event(id, title):
        return {
            "id": id,
            "summary": title,
            "start": {"date": "2026-11-01"},
            "end": {"date": "2026-11-02"},
        }

    def handler(request):
        owner = request.headers["authorization"].split()[-1]
        path = request.url.path
        if path.endswith("/calendarList"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": "same-calendar", "primary": True, "summary": "Fixture calendar"}
                    ]
                },
            )
        if phase[0] == 4:
            return httpx.Response(503)
        if path.endswith("/instances"):
            return httpx.Response(200, json={"items": [event("instance", "Recurring " + owner)]})
        token = request.url.params.get("syncToken")
        tokens.append(token)
        if phase[0] == 3 and token:
            return httpx.Response(410)
        items = [
            event("single", "One " + owner),
            {**event("series", "Series fixture"), "recurrence": ["RRULE:FREQ=DAILY;COUNT=2"]},
        ]
        if phase[0] == 2:
            items = [{"id": "single", "status": "cancelled"}]
        if phase[0] == 3:
            items = [event("replacement", "Replacement " + owner)]
        return httpx.Response(200, json={"items": items, "nextSyncToken": "token-" + str(phase[0])})

    def factory(engine, directory):
        helper = GoogleCalendarService(engine, directory)
        helper.http.close()
        helper.http = httpx.Client(transport=httpx.MockTransport(handler))
        return helper

    for owner, label in [(a, "fixture-a"), (b, "fixture-b")]:
        store.configure(
            owner,
            "google",
            {"access_token": label, "refresh_token": "fixture-refresh", "expires_at": 9999999999},
        )
        store.sync(owner, helper_factory=factory)
    assert len(store.events(a)) == 2
    assert all("fixture-a" in row["title"] for row in store.events(a))
    before_b = store.events(b)
    phase[0] = 2
    store.sync(a, helper_factory=factory)
    assert len(store.events(a)) == 1 and store.events(a)[0]["title"] == "Recurring fixture-a"
    assert "token-1" in tokens
    phase[0] = 3
    store.sync(a, helper_factory=factory)
    assert [row["title"] for row in store.events(a)] == ["Replacement fixture-a"]
    assert store.events(b) == before_b
    before_a = store.records(a, "google")
    phase[0] = 4
    with pytest.raises(GoogleProblem):
        store.sync(a, helper_factory=factory)
    assert store.records(a, "google") == before_a
    assert store.status(a, "google")["syncing"] is False
