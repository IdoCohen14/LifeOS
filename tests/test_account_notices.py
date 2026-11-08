import pytest
from lifeos.account_mail import AccountMail
from lifeos.account_notices import AccountNotices
from lifeos.account_preferences import AccountPreferences
from lifeos.account_providers import AccountProviders
from lifeos.account_records import AccountRecords
from lifeos.accounts import AccountService


def test_account_notices_and_recommendations_keep_receipts_and_source_actions_separate(
    client, setup_app
):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("notices-a", "fixture password a")
    b = auth.register("notices-b", "fixture password b")
    records = AccountRecords(engine)
    ta = records.save(a, "tasks", {"title": "Private deadline A", "due": "2000-01-01"})
    records.save(b, "tasks", {"title": "Private deadline B", "due": "2000-01-01"})
    assert (
        client.post(
            "/tasks", json={"title": "Legacy hidden fixture", "due": "2000-01-01"}
        ).status_code
        == 201
    )
    preferences = AccountPreferences(engine)
    provider = AccountProviders(engine, setup_app[1])
    for owner in (a, b):
        preferences.put(owner, "notifications", {"mail": True}, 0)
        provider.configure(owner, "gmail", {"refresh_token": "synthetic"})
        lease = provider.begin_sync(owner, "gmail")
        provider.commit_sync(
            owner,
            "gmail",
            lease["owner"],
            lease["revision"],
            [
                {
                    "id": "same-mail",
                    "subject": "Course fixture",
                    "sender": "Teacher <fixture@college.edu>",
                    "snippet": "Fixture",
                    "unread": True,
                    "received_at": 1000,
                }
            ],
        )
    notices = AccountNotices(engine)
    fa = notices.feed(a)
    fb = notices.feed(b)
    assert len(fa["items"]) == 2 and len(fb["items"]) == 2
    task_notice = next(row for row in fa["items"] if row["kind"] == "overdue")
    assert task_notice["source_ids"] == [ta["id"]]
    with pytest.raises(LookupError):
        notices.mutate(b, read_ids=[task_notice["id"]])
    mail_notice = next(row for row in fa["items"] if row["kind"] == "new_mail")
    assert any(row["id"] == mail_notice["id"] for row in fb["items"])
    notices.mutate(a, read_ids=[mail_notice["id"]])
    assert (
        next(row for row in notices.feed(b)["items"] if row["id"] == mail_notice["id"])["read"]
        is False
    )
    mail = AccountMail(engine)
    assert len(mail.get(a)["queue"]) == 1
    mail.review(a, mail.get(a)["revision"], message_id="same-mail")
    assert all(row["kind"] != "new_mail" for row in notices.feed(a)["items"])
    notices.mutate(a, action={"id": task_notice["id"], "action": "dismiss"})
    assert notices.feed(a)["hidden"][0]["id"] == task_notice["id"]
    notices.mutate(a, action={"id": task_notice["id"], "action": "restore"})
    assert notices.feed(a)["items"][0]["id"] == task_notice["id"]
    notices.mutate(a, dismiss_recommendation=task_notice["id"])
    assert notices.recommendations(a)["items"] == []
    assert len(notices.recommendations(b)["items"]) == 1

def test_notice_feed_includes_owned_course_and_genuine_sync_timestamp(client, setup_app):
    import json
    from datetime import datetime, timedelta, timezone

    from lifeos.account_academic import AccountAcademic
    from lifeos.account_notices import AccountNotices
    from lifeos.accounts import AccountService
    from lifeos.models import AccountMoodleChange, AccountProvider
    from sqlalchemy.orm import Session

    engine = setup_app[0].state.assistant.engine
    owner = AccountService(engine, enabled=True).register('context-fixture', 'fixture password')
    now = datetime.now(timezone.utc)
    academic = AccountAcademic(engine)
    term = academic.save_root(owner, 'terms', {'name':'Term','start_date':now.date().isoformat(),'end_date':(now+timedelta(days=30)).date().isoformat()})
    course = academic.save_root(owner, 'courses', {'name':'Owned course','term_id':term['id']})
    academic.save_child(owner, 'items', {'title':'Task fixture','course_id':course['id'],'due':(now+timedelta(days=1)).date().isoformat()})
    with Session(engine) as db:
        db.add(AccountProvider(account_id=owner, provider='moodle', last_success=int(now.timestamp())-5))
        db.add(AccountMoodleChange(account_id=owner,id='change-fixture',event_id='event-fixture',kind='added',current=json.dumps({'title':'Source fixture','start':now.date().isoformat()}),observed_at=int(now.timestamp())))
        db.commit()
    feed = AccountNotices(engine).feed(owner)
    task = next(item for item in feed['items'] if item['kind']=='due_soon')
    source = next(item for item in feed['items'] if item['kind']=='moodle_update')
    assert task['course_name']=='Owned course'
    assert 'source_updated_at' not in task
    assert source['source_updated_at']==int(now.timestamp())-5
    assert 'course_name' not in source

def test_upcoming_imported_event_retains_source_and_sync_time(client, setup_app):
    import json
    from datetime import datetime, timedelta, timezone

    from lifeos.account_notices import AccountNotices
    from lifeos.account_preferences import AccountPreferences
    from lifeos.accounts import AccountService
    from lifeos.models import AccountProvider, AccountProviderRecord
    from sqlalchemy.orm import Session

    engine = setup_app[0].state.assistant.engine
    owner = AccountService(engine, enabled=True).register('event-context', 'fixture password')
    AccountPreferences(engine).put(owner, 'notifications', {'events':True}, 0)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(AccountProvider(account_id=owner,provider='google',last_success=int(now.timestamp())))
        db.flush()
        db.add(AccountProviderRecord(account_id=owner,provider='google',external_id='fixture',payload=json.dumps({'kind':'visible','payload':{'id':'google-fixture','title':'Imported fixture','notes':'','start':(now+timedelta(hours=1)).isoformat(),'end':(now+timedelta(hours=2)).isoformat(),'all_day':False,'created_at':now.isoformat(),'source':'google'}})))
        db.commit()
    event = next(item for item in AccountNotices(engine).feed(owner)['items'] if item['kind']=='upcoming_event')
    assert event['event_source']=='google'
    assert event['source_updated_at']==int(now.timestamp())
