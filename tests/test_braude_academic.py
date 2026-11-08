import zipfile
from xml.sax.saxutils import escape

from lifeos.account_academic import AccountAcademic
from lifeos.account_braude import AccountBraude
from lifeos.accounts import AccountService
from lifeos.braude_academic import BraudeAcademic, read_roster


def roster_file(tmp_path):
    rows = [["סמסטר", "קוד נושא", "שם נושא", "סוג מקצוע", "מרצה"],
            ["א", "12345", "קורס דמה", "הרצאה", "מרצה דמה"],
            ["א", "12345", "קורס דמה (הערה:1)", "תרגיל", "מרצה דמה"]]
    xml = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    for i, row in enumerate(rows, 1):
        xml += f'<row r="{i}">'
        for j, value in enumerate(row):
            xml += f'<c r="{chr(65+j)}{i}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
        xml += '</row>'
    xml += '</sheetData></worksheet>'
    path = tmp_path / "official-fixture.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", xml)
    return path


def test_roster_collapses_teaching_sections_into_one_course(tmp_path):
    rows = read_roster(roster_file(tmp_path))
    assert rows == [{"code": "12345", "name": "קורס דמה", "instructor": "מרצה דמה"}]


def test_official_exam_snapshot_import_matches_course_code_and_is_idempotent(client, setup_app, tmp_path):
    from lifeos.braude_exams import BraudeExams

    engine = setup_app[0].state.assistant.engine
    owner = AccountService(engine, enabled=True).register("exam-fixture", "fixture password")
    BraudeAcademic(engine).import_roster(owner, roster_file(tmp_path), year=2027, semester=1,
                                       start_date="2026-10-02", end_date="2027-01-30")
    rows = [["קוד נושא", "שם נושא", "תאריך", "משך", "פקולטה", "חדר לימוד", "סמסטר", "מועד"],
            ["12345", "קורס דמה", '<time datetime="2027-02-04T08:30:00">04/02/2027</time>', "03:00", "", "טרם נקבע", "א", "1"]]
    xml = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    for i, row in enumerate(rows, 1):
        xml += '<row>' + ''.join(f'<c r="{chr(65+j)}{i}" t="inlineStr"><is><t>{escape(value)}</t></is></c>' for j, value in enumerate(row)) + '</row>'
    xml += '</sheetData></worksheet>'
    path = tmp_path / "exam-fixture.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", xml)
    service = BraudeExams(engine)
    assert service.import_exams(owner, path, year=2027, semester=1)["created"] == 1
    assert service.import_exams(owner, path, year=2027, semester=1)["existing"] == 1
    items = AccountAcademic(engine).list_children(owner, "items")
    assert len(items) == 1 and items[0]["kind"] == "exam"
    assert items[0]["due"] == "2027-02-04T06:30:00Z" and items[0]["duration_minutes"] == 180


def test_source_import_is_owned_idempotent_and_dated_events_are_not_repeated_templates(client, setup_app, tmp_path):
    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    accounts = AccountService(engine, enabled=True)
    owner = accounts.register("academic-source", "fixture password")
    other = accounts.register("academic-other", "fixture password")
    store = AccountBraude(engine, directory)
    store.configure(owner, "braude", {"url": "fixture"})
    event = {"id": "braude-fixture", "title": "קורס דמה מרצה דמה", "notes": "סוג מפגש: הרצאה", "source": "braude",
             "start": "2026-11-01T06:30:00Z", "end": "2026-11-01T08:00:00Z", "all_day": False, "created_at": "2026-01-01T00:00:00Z"}
    lease = store.begin_sync(owner, "braude")
    store.commit_sync(owner, "braude", lease["owner"], lease["revision"], [event])
    service = BraudeAcademic(engine)
    path = roster_file(tmp_path)
    args = dict(year=2027, semester=1, start_date="2026-10-02", end_date="2027-01-30")
    result = service.import_roster(owner, path, **args)
    service.import_roster(owner, path, **args)
    academic = AccountAcademic(engine)
    courses = academic.list_roots(owner, "courses")
    assert result["linked_events"] == 1 and len(courses) == 1
    assert courses[0]["source"] == "braude" and not courses[0]["credits_known"]
    assert academic.list_roots(other, "courses") == []
    assert academic.list_children(owner, "timetable") == []
    assert store.records(owner, "braude")[0]["course_id"] == courses[0]["id"]
    # Every later calendar refresh retains the source course relation.
    lease = store.begin_sync(owner, "braude")
    store.commit_sync(owner, "braude", lease["owner"], lease["revision"], [event])
    assert store.records(owner, "braude")[0]["course_id"] == courses[0]["id"]
