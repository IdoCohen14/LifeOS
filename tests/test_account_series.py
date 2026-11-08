from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from lifeos.account_records import AccountRecords
from lifeos.accounts import AccountService
from lifeos.recurring_events import RecurringEventService, RecurringInput
from lifeos.security import token_hash
from lifeos.series_management import DeleteInput, SeriesManagementService
from lifeos.series_rescheduling import RescheduleInput, SeriesReschedulingService


def test_owned_series_creation_rename_and_delete_remain_session_scoped(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("series-a", "fixture password a")
    b = auth.register("series-b", "fixture password b")
    sa = token_hash(auth.login("series-a", "fixture password a")["token"])
    sb = token_hash(auth.login("series-b", "fixture password b")["token"])
    day = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
    create = RecurringEventService(engine, account_id=a)
    manage = SeriesManagementService(engine, account_id=a)
    other = SeriesManagementService(engine, account_id=b)
    move = SeriesReschedulingService(engine, account_id=a)
    preview = create.preview(
        RecurringInput(title="Weekly fixture", day=day, count=2, timezone="Asia/Jerusalem"), sa
    )
    with pytest.raises(HTTPException):
        create.confirm(preview["id"], sb)
    result = create.confirm(preview["id"], sa)
    assert create.confirm(preview["id"], sa) == result
    assert len(AccountRecords(engine).list(a, "events")) == 2
    assert other.listing()["items"] == []
    assert SeriesManagementService(engine).listing()["items"] == []
    with pytest.raises(HTTPException):
        other.preview(result["series_id"], DeleteInput(from_day=day), sb)
    renamed = move.preview(
        result["series_id"], RescheduleInput(from_day=day, new_title="Renamed"), sa
    )
    assert move.confirm(renamed["id"], sa)["changed_count"] == 2
    deletion = manage.preview(result["series_id"], DeleteInput(from_day=day), sa)
    assert manage.confirm(deletion["id"], sa)["deleted_count"] == 2
    assert AccountRecords(engine).list(a, "events") == []
    assert other.listing()["items"] == []
