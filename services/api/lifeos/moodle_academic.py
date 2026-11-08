"""Explicit Moodle submission deadlines, atomically materialized as owned tasks."""

import json
import re
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field
from sqlalchemy import select

from .academic_models import AcademicItem, Course, Term
from .braude_academic import source_state
from .models import AccountPreference, Task


class MoodleAcademicState(BaseModel):
    entries: dict[str, dict[str, str]] = Field(default_factory=dict, max_length=10000)


def deadline_title(summary):
    # Explicit submission language only; never infer from "Lab 1" or a module URL.
    match = re.fullmatch(r"יש להגיש את ['\"](.+)['\"]", summary.strip())
    if match is None:
        match = re.fullmatch(r"(.+) is due(?: \(extension\))?", summary.strip())
    if match is None:
        # assign_update_events uses this explicit suffix for override events.
        match = re.fullmatch(r"(.+) \(Due date\)", summary.strip())
    return match[1].strip()[:240] if match and match[1].strip() else None


def capture(db, owner, events):
    pref = db.get(AccountPreference, (owner, "moodle_academic"))
    state = MoodleAcademicState.model_validate(json.loads(pref.payload) if pref else {})
    managed = source_state(db, owner)
    courses = db.execute(select(Course, Term).join(Term).where(
        Term.account_id == owner, Course.id.in_(managed.courses))).all()
    result = []
    for event in events:
        updated = dict(event)
        title = deadline_title(event["title"])
        hints = set()
        for category in event.get("course_categories", []):
            match = re.search(r"\(([0-9]{4})_([1-3])_[0-9]+_([0-9]{4,10})\)$", category.strip())
            if match:
                hints.add(tuple(match.groups()))
        matches = {course.id: course for course, term in courses
                   for year, semester, code in hints
                   if course.code == code and term.id == str(uuid5(
                       NAMESPACE_URL, f"{owner}/braude/{year}/{semester}"))}
        if len(matches) != 1:
            result.append(updated)
            continue
        course = next(iter(matches.values()))
        updated["course_id"] = course.id
        if not title:
            result.append(updated)
            continue
        item_id = str(uuid5(NAMESPACE_URL, f"{owner}/moodle/assignment/{event['id']}"))
        task_id = str(uuid5(NAMESPACE_URL, item_id + "/task"))
        previous = state.entries.get(event["id"])
        item = db.get(AcademicItem, item_id)
        if item is not None and (item.course_id != course.id or item.task.account_id != owner):
            raise PermissionError("Source assignment owner mismatch")
        values = {"title": title, "due": event["start"],
                  "notes": ("מקור: מועד הגשה ביומן Moodle. סימון בוצע כאן אינו הגשה במכללה.\n"
                            + event.get("source_url", "") + "\n" + event.get("notes", ""))[:10000]}
        if item is None and previous is None and len(state.entries) < 10000:
            task = Task(id=task_id, account_id=owner, title=title,
                        notes=values["notes"], due=values["due"], completed=False,
                        priority="high", created_at=datetime.now(timezone.utc).isoformat())
            db.add(task)
            db.flush()
            item = AcademicItem(id=item_id, course_id=course.id, task_id=task_id,
                                kind="assignment", effort_hours=0, duration_minutes=1, **values)
            db.add(item)
            db.flush()
        elif item is not None and previous is not None:
            # Three-way merge: changed source fields follow the source only while
            # both linked fields retain their last imported values. Never reopen.
            for key, value in values.items():
                if getattr(item, key) == previous.get(key) and getattr(item.task, key) == previous.get(key):
                    setattr(item, key, value)
                    setattr(item.task, key, value)
        if item is not None:
            updated["academic_id"] = item.id
            state.entries[event["id"]] = values
        result.append(updated)
    if state.entries:
        if pref is None:
            pref = AccountPreference(account_id=owner, kind="moodle_academic", revision=0)
            db.add(pref)
        pref.payload = state.model_dump_json()
        pref.revision += 1
    db.flush()
    return result


def visible_events(db, owner, events):
    """Suppress the feed copy only when the owned academic item still exists."""
    owned = set(db.scalars(select(AcademicItem.id).join(Course).join(Term).where(
        Term.account_id == owner, AcademicItem.kind == "assignment")))
    return [event for event in events if event.get("academic_id") not in owned]
