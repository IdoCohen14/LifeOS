import io
from datetime import datetime, timezone

import pytest
from lifeos.academic_models import Course
from lifeos.account_academic import AccountAcademic
from lifeos.accounts import AccountService
from lifeos.braude_academic import BraudeAcademic
from lifeos.braude_roster_preview import BraudeRosterPreview
from lifeos.local_release import preserved_rows
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_braude_academic import roster_file


@pytest.fixture
def roster_preview(client, setup_app, tmp_path):
    engine = setup_app[0].state.assistant.engine
    owner = AccountService(engine, enabled=True).register('roster-preview', 'fixture password')
    path = roster_file(tmp_path)
    BraudeAcademic(engine).import_roster(owner, path, year=2027, semester=1,
                                       start_date='2026-10-02', end_date='2027-01-30')
    metadata = dict(account_id=owner, observed_at=datetime.now(timezone.utc).isoformat(),
                    year=2027, semester=1, start_date='2026-10-02', end_date='2027-01-30', complete=True)
    return engine, owner, path.read_bytes(), metadata


def test_identical_roster_is_readonly_and_collapses_teaching_sections(roster_preview):
    engine, owner, content, source = roster_preview
    before = preserved_rows(engine.url.database)
    result = BraudeRosterPreview(engine).compare(owner, content, source)
    assert result['status'] == 'ready' and result['fixture'] is True
    assert result['counts'] == dict(unchanged=1, added=0, changed=0, missing=0)
    assert result['rows'][0]['code'] == '12345'
    assert preserved_rows(engine.url.database) == before


def test_missing_and_changed_are_reports_not_mutations(roster_preview):
    engine, owner, content, source = roster_preview
    with Session(engine) as db:
        course = db.scalar(select(Course))
        course.name = 'Local edited name'
        db.commit()
    before = preserved_rows(engine.url.database)
    result = BraudeRosterPreview(engine).compare(owner, content, source)
    assert result['counts']['changed'] == 1
    assert result['rows'][0]['fields'] == ['name']
    # Change the source code in the XLSX without altering the actual local course.
    import zipfile
    target = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as original, zipfile.ZipFile(target, 'w') as output:
        for name in original.namelist():
            output.writestr(name, original.read(name).replace(b'12345', b'99999'))
    result = BraudeRosterPreview(engine).compare(owner, target.getvalue(), source)
    assert result['counts'] == dict(unchanged=0, added=1, changed=0, missing=1)
    assert preserved_rows(engine.url.database) == before


@pytest.mark.parametrize('changes,reason', [
    ({'complete': False}, 'incomplete_source'),
    ({'semester': 2}, 'unsupported_semester'),
    ({'start_date': None}, 'missing_term_dates'),
    ({'start_date': '2026-10-03'}, 'term_mismatch'),
    ({'year': 2028}, 'unknown_term'),
    ({'observed_at': '2026-11-05T09:30:00'}, 'invalid_source'),
    ({'semester': None}, 'invalid_source'),
])
def test_ambiguous_source_never_claims_ready(roster_preview, changes, reason):
    engine, owner, content, source = roster_preview
    result = BraudeRosterPreview(engine).compare(owner, content, source | changes)
    assert result['status'] == 'needs_review' and result['reason'] == reason
    assert result['rows'] == []


def test_owner_mismatch_and_unknown_owner_are_denied(roster_preview):
    engine, owner, content, source = roster_preview
    other = AccountService(engine, enabled=True).register('other-roster', 'fixture password')
    with pytest.raises(PermissionError):
        BraudeRosterPreview(engine).compare(other, content, source)
    with pytest.raises(PermissionError):
        BraudeRosterPreview(engine).compare('missing-owner', content, source | {'account_id': 'missing-owner'})


@pytest.mark.parametrize('content', [b'not an export', b'x' * (4 * 1024 * 1024 + 1)], ids=['invalid', 'oversize'])
def test_bad_or_oversize_export_cannot_change_existing_data(roster_preview, content):
    engine, owner, _, source = roster_preview
    before = preserved_rows(engine.url.database)
    result = BraudeRosterPreview(engine).compare(owner, content, source)
    assert result['status'] == 'needs_review' and result['reason'] == 'invalid_export'
    assert preserved_rows(engine.url.database) == before


def test_unknown_instructor_is_explicit_and_not_a_false_change(roster_preview):
    import zipfile
    engine, owner, content, source = roster_preview
    target = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as original, zipfile.ZipFile(target, 'w') as output:
        for name in original.namelist():
            output.writestr(name, original.read(name).replace('מרצה דמה'.encode(), b''))
    result = BraudeRosterPreview(engine).compare(owner, target.getvalue(), source)
    assert result['rows'][0]['missing_fields'] == ['instructor']
    assert result['counts']['changed'] == 0


def test_manual_course_is_not_reported_as_removed(roster_preview):
    engine, owner, content, source = roster_preview
    academic = AccountAcademic(engine)
    term_id = academic.list_roots(owner, 'terms')[0]['id']
    academic.save_root(owner, 'courses', dict(term_id=term_id, name='Manual course', code='45678', instructor='', credits=0))
    result = BraudeRosterPreview(engine).compare(owner, content, source)
    assert result['counts']['missing'] == 0


@pytest.mark.parametrize('case', ['expanded-limit', 'mixed-semester', 'conflicting-name'])
def test_compressed_or_contradictory_export_is_rejected_without_writes(roster_preview, case):
    import zipfile
    engine, owner, content, source = roster_preview
    with zipfile.ZipFile(io.BytesIO(content)) as original:
        xml = original.read('xl/worksheets/sheet1.xml').decode('utf-8')
    if case == 'expanded-limit':
        xml = xml.replace('</sheetData>', ' ' * (4 * 1024 * 1024) + '</sheetData>')
    elif case == 'mixed-semester':
        xml = xml.replace('<t>א</t>', '<t>ב</t>', 1)
    else:
        xml = xml.replace('קורס דמה (הערה:1)', 'קורס אחר')
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr('xl/worksheets/sheet1.xml', xml)
    data = target.getvalue()
    assert len(data) < 4 * 1024 * 1024
    if case == 'expanded-limit':
        assert len(xml.encode('utf-8')) > 4 * 1024 * 1024
    before = preserved_rows(engine.url.database)
    result = BraudeRosterPreview(engine).compare(owner, data, source)
    assert result['status'] == 'needs_review' and result['reason'] == 'invalid_export'
    assert result['rows'] == []
    assert preserved_rows(engine.url.database) == before
