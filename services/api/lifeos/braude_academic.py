"""Owned academic roster from an official export, linked to dated subscription events."""

import json
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .academic_models import Course, Term
from .academic_schemas import TermInput
from .account_records import AccountRecords
from .models import AccountPreference, AccountProviderRecord


class BraudeAcademicState(BaseModel):
    courses: dict[str, str] = Field(default_factory=dict, max_length=2000)
    term_ids: list[str] = Field(default_factory=list, max_length=100)
    observed_at: int = 0


def sheet_rows(path):
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        if sum(info.file_size for info in archive.infolist()) > 4 * 1024 * 1024:
            raise ValueError("Roster too large")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(row.itertext()) for row in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("m:si", ns)]
        xml = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in xml.findall(".//m:row", ns):
            values = {}
            for cell in row.findall("m:c", ns):
                value = cell.find("m:v", ns)
                text = (strings[int(value.text)] if cell.get("t") == "s" and value is not None
                        else "".join(cell.find("m:is", ns).itertext()) if cell.get("t") == "inlineStr"
                        else value.text if value is not None else "")
                values[re.sub(r"[0-9]", "", cell.get("r", ""))] = str(text).strip()
            rows.append(values)
    return rows


def read_roster(path):
    rows = sheet_rows(path)
    header = next((i for i, row in enumerate(rows) if row.get("B") == "קוד נושא" and row.get("C") == "שם נושא"), None)
    if header is None:
        raise ValueError("Unrecognized official roster headers")
    result = {}
    for row in rows[header + 1:]:
        if not row.get("B"):
            continue
        code = row["B"]
        # Yedion appends a numbered note to some teaching sections of the same
        # registered course. It is annotation metadata, not a second course name.
        name = re.sub(r"\s*\(הערה:\s*[0-9]+\)\s*$", "", row.get("C", ""))
        if not re.fullmatch(r"[0-9]{4,10}", code) or not name or len(name) > 160 or row.get("A") != "א":
            raise ValueError("Invalid or mixed-semester roster")
        entry = result.setdefault(code, {"code": code, "name": name, "instructors": set()})
        if entry["name"] != name:
            raise ValueError("Conflicting source course names")
        if row.get("E"):
            entry["instructors"].add(row["E"])
    if not 1 <= len(result) <= 100:
        raise ValueError("Empty or oversized roster")
    return [{"code": row["code"], "name": row["name"], "instructor": " / ".join(sorted(row["instructors"]))[:120]}
            for row in result.values()]


def source_state(db, owner):
    row = db.get(AccountPreference, (owner, "braude_academic"))
    return BraudeAcademicState.model_validate(json.loads(row.payload) if row else {})


def enrich_events(db, owner, events):
    state = source_state(db, owner)
    if not state.courses:
        return events
    courses = db.execute(select(Course, Term).join(Term).where(
        Term.account_id == owner, Course.id.in_(state.courses))).all()
    def normalize(text):
        return re.sub(r"[^\w\u0590-\u05ff]", "", text).casefold()
    result = []
    for event in events:
        updated = {k: v for k, v in event.items() if k != "course_id"}
        if not event["all_day"] and re.search(r"הרצאה|תרגיל|תרגול|מעבדה", event["notes"]):
            day = datetime.fromisoformat(event["start"].replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Jerusalem")).date().isoformat()
            matches = [course.id for course, term in courses
                       if term.start_date <= day <= term.end_date
                       and normalize(event["title"]).startswith(normalize(state.courses[course.id]))]
            if len(matches) == 1:
                updated["course_id"] = matches[0]
        result.append(updated)
    return result


class BraudeAcademic(AccountRecords):
    def import_roster(self, owner, path, *, year, semester, start_date, end_date):
        # Dates are required from the portal's explicit term legend; never inferred
        # from the first/last calendar event, which can include holidays.
        if semester != 1 or not 2000 <= year <= 2100:
            raise ValueError("Unsupported source semester")
        term_values = TermInput(name=f"בראודה {year} · סמסטר א׳", start_date=start_date, end_date=end_date).model_dump(mode="json")
        roster = read_roster(path)
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, owner)
            state = source_state(db, owner)
            term_id = str(uuid5(NAMESPACE_URL, f"{owner}/braude/{year}/{semester}"))
            term = db.get(Term, term_id)
            if term is None:
                term = Term(id=term_id, account_id=owner, **term_values)
                db.add(term)
                db.flush()
            elif term.account_id != owner:
                raise PermissionError("Academic owner mismatch")
            elif term.start_date != start_date or term.end_date != end_date:
                raise ValueError("Existing term dates differ; explicit review needed")
            for row in roster:
                course_id = str(uuid5(NAMESPACE_URL, f"{owner}/braude/{year}/{semester}/{row['code']}"))
                course = db.get(Course, course_id)
                if course is None:
                    course = Course(id=course_id, term_id=term_id, **row, credits=0)
                    db.add(course)
                elif course.term_id != term_id:
                    raise PermissionError("Course owner mismatch")
                # Do not overwrite existing user edits on repeated source import.
                state.courses[course_id] = row["name"]
            state.term_ids = sorted(set(state.term_ids) | {term_id})
            state.observed_at = int(time.time())
            pref = db.get(AccountPreference, (owner, "braude_academic"))
            if pref is None:
                pref = AccountPreference(account_id=owner, kind="braude_academic", revision=0, payload="{}")
                db.add(pref)
            pref.payload, pref.revision = state.model_dump_json(), pref.revision + 1
            db.flush()
            rows = list(db.scalars(select(AccountProviderRecord).where(
                AccountProviderRecord.account_id == owner, AccountProviderRecord.provider == "braude")))
            enriched = enrich_events(db, owner, [json.loads(row.payload) for row in rows])
            for row, event in zip(rows, enriched, strict=True):
                row.payload = json.dumps(event, ensure_ascii=False)
            db.commit()
        return {"courses": len(roster), "term_id": term_id, "linked_events": sum("course_id" in e for e in enriched)}
