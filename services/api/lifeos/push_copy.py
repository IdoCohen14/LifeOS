"""Bounded notification copy from existing, freshly validated notice candidates."""

import math
import re
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .academic_models import AcademicItem, Course, Term
from .models import Task
from .moodle_academic import deadline_title


def with_owned_course(db, owner, item):
    if owner is not None and item.get("lesson") and item.get("course_id"):
        course = db.scalar(select(Course).join(Term).where(Course.id == item['course_id'], Term.account_id == owner))
        if course is not None:
            return {**item, "course_name": course.name, "instructor": course.instructor}
        return item
    if owner is None or item.get("kind") not in ("due_soon", "overdue", "moodle_update"):
        return item
    ids = item.get("source_ids", [])[:10]
    condition = AcademicItem.task_id.in_(ids)
    if item.get("kind") == "moodle_update":
        condition = AcademicItem.id.in_([
            str(uuid5(NAMESPACE_URL, f"{owner}/moodle/assignment/{id}")) for id in ids
        ])
    names = set(db.execute(
        select(Course.name, AcademicItem.kind).join(AcademicItem, AcademicItem.course_id == Course.id)
        .join(Term, Term.id == Course.term_id).join(Task, Task.id == AcademicItem.task_id)
        .where(Term.account_id == owner, Task.account_id == owner, condition).limit(11)
    ).all())
    if len(names) != 1:
        return item
    name, kind = next(iter(names))
    return {**item, "course_name": name, "academic_kind": kind}


def clean(value, limit):
    text = re.sub(r"[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]", " ", str(value or ""))
    return " ".join(text.split()).encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def notification_copy(item, language, zone, now):
    he = language == "he"
    name = clean(item.get("title"), 150)
    course = clean(item.get("course_name"), 100)
    if course:
        name = f"{clean(item.get('title'), 100)} · {course}"
    kind = item.get("kind")
    title = "עדכון מ־LifeOS" if he else "LifeOS update"
    body = name
    if kind in ("due_soon", "overdue"):
        title = ("מועד הגשה מתקרב" if he else "Deadline approaching") if kind == "due_soon" else ("מועד ההגשה עבר" if he else "Deadline passed")
        due = item.get("due", "")
        if len(due) == 10:
            body = f"{name} — {due}"
        else:
            try:
                instant = datetime.fromisoformat(due.replace("Z", "+00:00"))
                if instant.utcoffset() is None:
                    raise ValueError()
                hours = (instant - now).total_seconds() / 3600
                if hours > 0:
                    remaining = (f"בעוד כ־{math.ceil(hours)} שעות" if he else f"in about {math.ceil(hours)} hours") if hours >= 1 else ("בעוד פחות משעה" if he else "in less than an hour")
                    body = f"מועד ההגשה של {name} {remaining}" if he else f"{name} is due {remaining}"
                else:
                    body = f"{name} — {instant.astimezone(ZoneInfo(zone)):%d/%m/%Y %H:%M}"
            except (ValueError, TypeError):
                body = name
    elif kind == "moodle_update":
        assignment = deadline_title(item.get("title", ""))
        body = clean(assignment, 100) if assignment else name
        if assignment and course:
            body = f"{body} · {course}"
        change = item.get("change_kind")
        title = ("נוספה מטלה" if he else "Assignment added") if assignment and change == "added" else ("נוסף מועד ב־Moodle" if he else "Moodle deadline added") if change == "added" else ("מועד עודכן ב־Moodle" if he else "Moodle deadline updated") if change == "changed" else ("מועד הוסר מהמקור" if he else "Deadline removed from source")
    elif kind == "conflict":
        title = "התנגשות בזמנים" if he else "Schedule conflict"
    elif kind == "upcoming_event":
        title = "אירוע מתקרב" if he else "Upcoming event"
        if item.get("lesson"):
            title = ("שיעור הבא — " if he else "Next class — ") + (course or name)
            room = clean(item.get("class_room"), 70)
            lecturer = clean(item.get("instructor"), 90)
            body = (f"כיתה {room}" if he and room else f"Room {room}" if room else "כיתה לא צוינה במקור" if he else "Room not provided by source") + " · " + (lecturer or ("מרצה לא צוין במקור" if he else "Lecturer not provided by source"))
            start = datetime.fromisoformat(item['start'].replace('Z', '+00:00'))
            if start.utcoffset() is not None:
                local = start.astimezone(ZoneInfo(zone))
                # Keep the installed worker's strict wire contract: older workers
                # still display the copy; updated workers recognize this dated lesson.
                return {"notice_title": clean(title, 100), "notice_body": clean(f"{local:%Y-%m-%d %H:%M} · {body}", 300)}
    elif kind == "new_mail":
        title = "מייל חדש" if he else "New email"
    elif kind == "request_followup":
        title = "זמן לחזור לבקשה" if he else "Time to revisit a request"
    elif kind in ("daily_briefing", "weekly_briefing"):
        title = ("הסיכום היומי מוכן" if he else "Daily briefing ready") if kind == "daily_briefing" else ("הסיכום השבועי מוכן" if he else "Weekly review ready")
    return {"notice_title": clean(title, 100), "notice_body": clean(body, 300)}
