from datetime import datetime, timezone

from lifeos.push_copy import notification_copy


def test_explicit_task_copy_and_date_only_are_honest():
    now = datetime(2026, 11, 3, 8, tzinfo=timezone.utc)
    def copy(item):
        return notification_copy(item, 'he', 'Asia/Jerusalem', now)
    assert copy({'kind': 'moodle_update', 'change_kind': 'added', 'title': "יש להגיש את 'תרגיל 2'"}) == {'notice_title': 'נוספה מטלה', 'notice_body': 'תרגיל 2'}
    assert '24 שעות' in copy({'kind': 'due_soon', 'title': 'תרגיל 2', 'due': '2026-11-04T08:00:00Z'})['notice_body']
    assert 'שעות' not in copy({'kind': 'due_soon', 'title': 'תרגיל 2', 'due': '2026-11-04'})['notice_body']
    assert copy({'kind': 'moodle_update', 'change_kind': 'removed', 'title': 'Test'})['notice_title'] == 'מועד הוסר מהמקור'
    value = copy({'kind': 'conflict', 'title': '\u202e\n' + '😀' * 500})
    assert len(value['notice_body'].encode()) <= 300
    assert '\u202e' not in value['notice_body']


def test_course_name_appears_in_assignment_and_deadline_copy():
    now = datetime(2026, 11, 3, 8, tzinfo=timezone.utc)
    added = notification_copy({'kind': 'moodle_update', 'change_kind': 'added', 'title': "יש להגיש את 'מטלה 1'", 'course_name': 'מערכות הפעלה'}, 'he', 'Asia/Jerusalem', now)
    assert added['notice_body'] == 'מטלה 1 · מערכות הפעלה'
    due = notification_copy({'kind': 'due_soon', 'title': 'מטלה 1', 'course_name': 'מערכות הפעלה', 'due': '2026-11-04T08:00:00Z'}, 'he', 'Asia/Jerusalem', now)
    assert 'מטלה 1 · מערכות הפעלה' in due['notice_body']


def test_course_lookup_is_owned_and_only_uses_linked_academic_item(client, setup_app):
    from uuid import NAMESPACE_URL, uuid5

    from lifeos.academic_models import AcademicItem
    from lifeos.account_academic import AccountAcademic
    from lifeos.accounts import AccountService
    from lifeos.push_copy import with_owned_course
    from sqlalchemy.orm import Session

    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    owner = accounts.register('course-notice', 'fixture password')
    other = accounts.register('course-other', 'fixture password')
    store = AccountAcademic(engine)
    term = store.save_root(owner, 'terms', {'name': 'Term', 'start_date': '2026-10-01', 'end_date': '2027-02-01'})
    course = store.save_root(owner, 'courses', {'name': 'Operating Systems', 'term_id': term['id']})
    item = store.save_child(owner, 'items', {'course_id': course['id'], 'title': 'Assignment 1', 'due': '2026-11-04'})
    notice = {'kind': 'due_soon', 'source_ids': [item['task_id']]}
    with Session(engine) as db:
        assert with_owned_course(db, owner, notice)['course_name'] == 'Operating Systems'
        assert 'course_name' not in with_owned_course(db, other, notice)
        assert 'course_name' not in with_owned_course(db, owner, {'kind': 'due_soon', 'source_ids': ['missing']})
        linked = db.get(AcademicItem, item['id'])
        linked.id = str(uuid5(NAMESPACE_URL, f"{owner}/moodle/assignment/source-fixture"))
        db.flush()
        added = {'kind': 'moodle_update', 'source_ids': ['source-fixture']}
        assert with_owned_course(db, owner, added)['course_name'] == 'Operating Systems'
        assert 'course_name' not in with_owned_course(db, other, added)
