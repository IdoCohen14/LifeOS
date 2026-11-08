"""Official exam roster snapshot, matched to owned courses by source code."""

import re
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .academic_calendar import local_utc
from .academic_models import AcademicItem, Course, Term
from .account_records import AccountRecords
from .braude_academic import sheet_rows
from .models import Task


def read_exams(path):
    rows = sheet_rows(path)
    header = next((i for i, row in enumerate(rows) if row.get("A") == "קוד נושא" and row.get("C") == "תאריך" and row.get("H") == "מועד"), None)
    if header is None:
        raise ValueError("Unrecognized exam roster")
    result = []
    for row in rows[header + 1:]:
        if not row.get("A"):
            continue
        if not re.fullmatch(r"[0-9]{4,10}", row["A"]) or row.get("G") != "א" or row.get("H") not in {"1", "2", "3"}:
            raise ValueError("Invalid exam code/semester/round")
        match = re.search(r'<time\s+datetime="([0-9T:\-]+)"', row.get("C", ""))
        if not match:
            raise ValueError("Explicit exam timestamp required")
        local = datetime.fromisoformat(match[1])
        due = local_utc(local.date(), local.time().isoformat(), "Asia/Jerusalem")
        duration = re.fullmatch(r"([0-9]{1,2}):([0-5][0-9])", row.get("D", ""))
        if not duration:
            raise ValueError("Explicit exam duration required")
        minutes = int(duration[1]) * 60 + int(duration[2])
        if not 1 <= minutes <= 720:
            raise ValueError("Invalid exam duration")
        result.append({"code": row["A"], "round": int(row["H"]), "due": due,
                       "duration_minutes": minutes, "room": row.get("F", "")[:240]})
    if not 1 <= len(result) <= 1000 or len({(x["code"], x["round"]) for x in result}) != len(result):
        raise ValueError("Empty or duplicate exam roster")
    return result


class BraudeExams(AccountRecords):
    def import_exams(self, owner, path, *, year, semester):
        if semester != 1 or not 2000 <= year <= 2100:
            raise ValueError("Unsupported semester")
        source = read_exams(path)
        term_id = str(uuid5(NAMESPACE_URL, f"{owner}/braude/{year}/{semester}"))
        created = existing = 0
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, owner)
            term = db.get(Term, term_id)
            if term is None or term.account_id != owner:
                raise ValueError("Verified source term required")
            courses = {c.code: c for c in db.scalars(select(Course).where(Course.term_id == term_id))}
            if any(row["code"] not in courses for row in source):
                raise ValueError("Exam course not found; no partial import")
            for row in source:
                course = courses[row["code"]]
                item_id = str(uuid5(NAMESPACE_URL, f"{owner}/braude/exam/{year}/{semester}/{row['code']}/{row['round']}"))
                item = db.get(AcademicItem, item_id)
                if item is not None:
                    if item.course_id != course.id:
                        raise PermissionError("Exam owner mismatch")
                    if item.due != row["due"] or item.duration_minutes != row["duration_minutes"]:
                        raise ValueError("Existing source exam changed; review required")
                    existing += 1
                    continue
                # Do not duplicate a manually entered exam at this exact course/time.
                match = db.scalar(select(AcademicItem).where(AcademicItem.course_id == course.id,
                    AcademicItem.kind == "exam", AcademicItem.due == row["due"]))
                if match:
                    existing += 1
                    continue
                title = f"מבחן · {course.name} · מועד {row['round']}"[:240]
                notes = "מקור: לוח הבחינות בתחנת המידע. מועד שפורסם אינו אישור רישום לבחינה.\nחדר: " + (row["room"] or "טרם פורסם")
                task = Task(id=str(uuid5(NAMESPACE_URL, item_id + "/task")), account_id=owner,
                    title=title, notes=notes, due=row["due"], completed=False, priority="high",
                    created_at=datetime.now(timezone.utc).isoformat())
                db.add(task)
                db.flush()
                db.add(AcademicItem(id=item_id, course_id=course.id, task_id=task.id,
                    title=title, notes=notes, kind="exam", due=row["due"], effort_hours=0,
                    duration_minutes=row["duration_minutes"]))
                db.flush()
                created += 1
            db.commit()
        return {"created": created, "existing": existing, "source_exams": len(source)}
