from datetime import datetime, timezone

import pytest
from lifeos.account_planning import AccountPlanning
from lifeos.account_records import AccountRecords
from lifeos.accounts import AccountService


def test_owned_planning_requires_same_session_confirmation_and_rechecks_conflicts(
    client, setup_app
):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("plan-a", "fixture password a")
    b = auth.register("plan-b", "fixture password b")
    sa = auth.login("plan-a", "fixture password a")
    sb = auth.login("plan-b", "fixture password b")
    records = AccountRecords(engine)
    task = records.save(a, "tasks", {"title": "Planning fixture"})
    planning = AccountPlanning(engine)
    now = datetime(2026, 10, 30, 4, tzinfo=timezone.utc)
    body = {
        "task_id": task["id"],
        "day": "2026-10-30",
        "duration": 30,
        "window_start": "08:00",
        "window_end": "12:00",
    }
    proposal = planning.propose(a, sa["token"], body, now=now)["proposal"]
    competing = planning.propose(a, sa["token"], {**body, "window_start": "10:00"}, now=now)[
        "proposal"
    ]
    assert records.list(a, "events") == []
    with pytest.raises(LookupError):
        planning.confirm(b, sb["token"], proposal["id"], now=now)
    saved = planning.confirm(a, sa["token"], proposal["id"], now=now)
    with pytest.raises(ValueError):
        planning.confirm(a, sa["token"], competing["id"], now=now)
    assert planning.confirm(a, sa["token"], proposal["id"], now=now) == saved
    assert len(records.list(a, "events")) == 1 and records.list(b, "events") == []
    assert records.list(a, "tasks")[0]["completed"] is False
    another = records.save(a, "tasks", {"title": "Other fixture"})
    next_proposal = planning.propose(a, sa["token"], {**body, "task_id": another["id"]}, now=now)[
        "proposal"
    ]
    records.save(a, "events", next_proposal["record"])
    with pytest.raises(ValueError):
        planning.confirm(a, sa["token"], next_proposal["id"], now=now)
