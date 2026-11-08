import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import pytest
from lifeos import academic_review
from lifeos.account_academic import AccountAcademic
from lifeos.account_providers import AccountProviders
from lifeos.account_records import AccountRecords
from lifeos.account_snapshot import AccountSnapshot
from lifeos.accounts import AccountService
from lifeos.braude_academic import BraudeAcademic
from lifeos.braude_exams import BraudeExams
from lifeos.models import Task
from sqlalchemy.orm import Session
from test_braude_academic import roster_file


def exam_export(path):
    rows = [['קוד נושא','שם נושא','תאריך','משך','פקולטה','חדר לימוד','סמסטר','מועד'],
            ['12345','קורס דמה','<time datetime="2027-02-04T08:30:00">04/02/2027</time>','03:00','','A123','א','1']]
    xml = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    for values in rows:
        xml += '<row>' + ''.join(f'<c r="{chr(65+i)}1" t="inlineStr"><is><t>{escape(value)}</t></is></c>' for i,value in enumerate(values)) + '</row>'
    xml += '</sheetData></worksheet>'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('xl/worksheets/sheet1.xml', xml)
    return path


@pytest.mark.parametrize('manual_exam', [False, True], ids=['new-official-exam','matching-manual-exam'])
def test_repeated_exam_import_counts_one_date_without_hiding_personal_or_google(client, setup_app, tmp_path, monkeypatch, manual_exam):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owner = auth.register('exam-counts', 'fixture password')
    other = auth.register('exam-counts-other', 'fixture password')
    BraudeAcademic(engine).import_roster(owner, roster_file(tmp_path), year=2027, semester=1,
                                       start_date='2026-10-02', end_date='2027-01-30')
    academic = AccountAcademic(engine)
    course = academic.list_roots(owner, 'courses')[0]
    if manual_exam:
        academic.save_child(owner, 'items', dict(course_id=course['id'], title='Manual exam fixture',
                                                kind='exam', due='2027-02-04T06:30:00Z', duration_minutes=180))
    records = AccountRecords(engine)
    task = records.save(owner, 'tasks', dict(title='Task fixture', due='2027-02-04'))
    event = dict(title='Same-time personal fixture', start='2027-02-04T06:30:00Z',
                 end='2027-02-04T09:30:00Z', all_day=False)
    records.save(owner, 'events', event)
    providers = AccountProviders(engine, setup_app[1])
    providers.configure(owner, 'google', {'refresh_token':'synthetic'})
    lease = providers.begin_sync(owner, 'google')
    providers.commit_sync(owner, 'google', lease['owner'], lease['revision'], [
        dict(id='google-visible-fixture', kind='visible', payload=event | dict(
            id='google-event-fixture', source='google', created_at='2026-01-01T00:00:00Z'))])
    snapshots = AccountSnapshot(engine)
    before = snapshots.build(owner)
    source = exam_export(tmp_path / 'exam-fixture.xlsx')
    importer = BraudeExams(engine)
    first = importer.import_exams(owner, source, year=2027, semester=1)
    assert first['created'] == (0 if manual_exam else 1)
    assert importer.import_exams(owner, source, year=2027, semester=1)['existing'] == 1
    after = snapshots.build(owner)
    assert len(after['events']) == len(before['events']) + (0 if manual_exam else 1)
    assert len([event for event in after['events'] if event.get('source') == 'exam']) == 1
    assert len([event for event in after['events'] if event.get('source') == 'google']) == 1
    assert len([event for event in after['events'] if event.get('source', 'personal') == 'personal']) == 1
    assert [row['id'] for row in after['tasks']] == [task['id']]
    now = datetime(2027, 2, 4, 6, tzinfo=timezone.utc)
    summary = snapshots.briefing(owner, now=now)
    assert summary['events'] == 3 and summary['deadlines'] == 1
    assert snapshots.build(other)['events'] == []

    # Legacy completion metadata cannot remove a future exam date or inflate tasks.
    item = academic.list_children(owner, 'items')[0]
    with Session(engine) as db:
        db.get(Task, item['task_id']).completed = True
        db.commit()
    monkeypatch.setattr(academic_review, 'current_time', lambda: now)
    assert academic_review.academic_snapshot(engine, account_id=owner)['exams_total'] == 1
    assert snapshots.briefing(owner, now=now)['deadlines'] == 1
