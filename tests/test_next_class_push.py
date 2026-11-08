from datetime import datetime, timedelta, timezone

from lifeos.account_academic import AccountAcademic
from lifeos.account_notices import AccountNotices
from lifeos.account_preferences import AccountPreferences
from lifeos.accounts import AccountService
from lifeos.push_copy import notification_copy


def test_lesson_reminder_is_timed_owned_and_not_an_exam(client, setup_app, monkeypatch):
    from lifeos.web_push import ConfigInput, WebPushService
    from lifeos.web_push_delivery import PushDeliveryService
    from lifeos.web_push_transport import SubscriptionInput
    from test_web_push_transport import subscription
    engine = setup_app[0].state.assistant.engine
    owner = AccountService(engine, enabled=True).register('lesson-fixture', 'fixture password')
    prefs = AccountPreferences(engine)
    prefs.put(owner, 'notifications', {'quiet_enabled': False}, 0)
    prefs.put(owner, 'secretary', {'class_reminder_minutes': 10}, 0)
    academic = AccountAcademic(engine)
    term = academic.save_root(owner, 'terms', {'name': 'Fixture', 'start_date': '2026-10-01', 'end_date': '2027-02-01'})
    course = academic.save_root(owner, 'courses', {'name': 'מערכות הפעלה', 'instructor': 'מרצה הדגמה', 'term_id': term['id']})
    academic.save_child(owner, 'timetable', {'course_id': course['id'], 'weekday': 3, 'start_time': '14:00', 'end_time': '15:00', 'timezone': 'Asia/Jerusalem', 'location': 'L709'})
    academic.save_child(owner, 'items', {'course_id': course['id'], 'title': 'מבחן', 'kind': 'exam', 'due': '2026-11-04T16:00:00+02:00'})
    class Clock(datetime):
        instant = datetime(2026, 11, 4, 11, 49, tzinfo=timezone.utc)
        @classmethod
        def now(cls, tz=None):
            return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)
    monkeypatch.setattr('lifeos.account_notices.datetime', Clock)
    def lessons():
        return [v for v in AccountNotices(engine).feed(owner)['items'] if v.get('lesson')]
    assert lessons() == []
    Clock.instant += timedelta(minutes=1)
    value, = lessons()
    assert value['target'] == 'timetable'
    assert value['course_name'] == 'מערכות הפעלה'
    copy = notification_copy(value, 'he', 'Asia/Jerusalem', Clock.instant)
    assert copy['notice_title'] == 'שיעור הבא — מערכות הפעלה'
    assert 'L 709' in copy['notice_body'] and 'מרצה הדגמה' in copy['notice_body']
    first_id = value['id']
    # Delivered notices may remain unread: they must not consume the entire feed
    # before the short-lived class reminder can reach the Push worker.
    monkeypatch.setattr('lifeos.account_notices.RecommendationService.candidates', lambda *args, **kwargs: ([{'id': f'{i:064x}', 'kind': 'overdue', 'title': 'Old fixture', 'due': '2026-10-01', 'target': 'tasks', 'priority': 1, 'order': '2026-10-01', 'source_ids': []} for i in range(20)], False))
    assert AccountNotices(engine).feed(owner)['items'][0].get('lesson')
    push = WebPushService(engine, setup_app[1], account_id=owner)
    push.configure(ConfigInput(contact='fixture@example.test', revision=0))
    push.register(SubscriptionInput.model_validate(subscription()))
    monkeypatch.setattr('lifeos.web_push_delivery.current_time', lambda: Clock.instant)
    sent = []
    worker = PushDeliveryService(engine, setup_app[1], account_id=owner, sender=lambda s, k, c, payload: sent.append(payload) or (201, 0))
    assert worker.run_due() == 1
    assert sent[0]['notice_title'] == 'שיעור הבא — מערכות הפעלה'
    assert sent[0]['notice_body'].startswith('2026-11-04 14:00 · ')
    assert 'notice_url' not in sent[0]  # Already-installed workers reject extra wire fields.
    assert worker.run_due() == 0
    Clock.instant += timedelta(minutes=1)
    assert lessons()[0]['id'] == first_id
    Clock.instant += timedelta(minutes=9)
    assert lessons() == []
    Clock.instant += timedelta(days=7, minutes=-9)
    assert lessons()[0]['id'] != first_id


def test_lesson_copy_honest_fallback_and_safe_destination():
    now = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
    item = {'kind': 'upcoming_event', 'lesson': True, 'title': 'קורס הדגמה', 'start': '2026-11-04T14:10:00+02:00'}
    value = notification_copy(item, 'he', 'Asia/Jerusalem', now)
    assert value['notice_title'] == 'שיעור הבא — קורס הדגמה'
    assert 'כיתה לא צוינה במקור' in value['notice_body']
    assert 'מרצה לא צוין במקור' in value['notice_body']
    assert value['notice_body'].startswith('2026-11-04 14:10 · ')
    assert 'notice_url' not in notification_copy({**item, 'lesson': False}, 'he', 'Asia/Jerusalem', now)


def test_official_class_classification_and_room_do_not_guess():
    from lifeos.class_reminders import class_room, is_class_event
    teaching = {'source': 'braude', 'title': 'מערכות הפעלה', 'notes': 'הרצאה\nחדר: 709 L', 'all_day': False}
    assert is_class_event(teaching)
    assert class_room(teaching) == 'L 709'
    assert not is_class_event({**teaching, 'title': 'מבחן מערכות הפעלה'})
    assert not is_class_event({**teaching, 'source': 'google'})
    assert not is_class_event({**teaching, 'all_day': True})
    assert class_room({**teaching, 'notes': 'הרצאה'}) == ''
