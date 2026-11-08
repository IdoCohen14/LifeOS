"""Current manual academic snapshot for time-management review, not publication history."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from . import academic_reads
from .academic_models import AcademicItem, Course, Grade, Term
from .account_records import AccountRecords
from .assistant import scoped_settings
from .models import Task


def current_time():
    return datetime.now(timezone.utc)


def academic_snapshot(engine, *, account_id=None):
    now = current_time()
    budget = academic_reads.ReadBudget()
    with Session(engine) as db:
        db.execute(text("BEGIN"))
        if account_id is not None:
            AccountRecords(engine).authorize(db, account_id)
        zone_name = scoped_settings(db, account_id).timezone
        zone = ZoneInfo(zone_name)
        today = now.astimezone(zone).date()
        until = today + timedelta(days=7)
        rows = db.execute(
            select(
                Course.id.label("course_id"),
                Course.name.label("course_name"),
                Term.name.label("term_name"),
                func.count(Grade.id).label("grade_count"),
                func.coalesce(func.sum(Grade.weight), 0).label("known_weight"),
                func.coalesce(
                    func.sum(Grade.score * 100.0 / Grade.maximum * func.coalesce(Grade.weight, 0)),
                    0,
                ).label("weighted_sum"),
            )
            .join(Grade, Grade.course_id == Course.id)
            .join(Term, Term.id == Course.term_id)
            .where(Term.account_id == account_id)
            .group_by(Course.id, Course.name, Term.name)
            .order_by(Term.name, Course.name, Course.id)
            .limit(11)
        ).all()
        budget.check()
        grades = [
            {
                "course_id": row.course_id,
                "course_name": row.course_name,
                "term_name": row.term_name,
                "grade_count": row.grade_count,
                "known_weight": round(row.known_weight, 2),
                "weighted_percent": round(row.weighted_sum / row.known_weight, 2)
                if row.known_weight
                else None,
            }
            for row in rows[:10]
        ]
        exams = []
        assignments = []
        query = (
            select(
                AcademicItem.id,
                AcademicItem.title,
                AcademicItem.kind,
                AcademicItem.effort_hours,
                AcademicItem.due,
                AcademicItem.task_id,
                AcademicItem.course_id,
                Course.name.label("course_name"),
                Term.name.label("term_name"),
            )
            .join(Course, Course.id == AcademicItem.course_id)
            .join(Term, Term.id == Course.term_id)
            .join(Task, Task.id == AcademicItem.task_id)
            .where(
                Term.account_id == account_id,
                Task.account_id == account_id,
                AcademicItem.kind.in_(("exam", "assignment")),
                or_(AcademicItem.kind == "exam", Task.completed.is_(False)),
            )
            .limit(academic_reads.MAX_RECORDS + 1)
        )
        for index, row in enumerate(db.execute(query).yield_per(200)):
            budget.check()
            if index >= academic_reads.MAX_RECORDS:
                raise HTTPException(503, "academic_resource_limit")
            instant = (
                None
                if len(row.due) == 10
                else datetime.fromisoformat(row.due.replace("Z", "+00:00"))
            )
            day = (
                date.fromisoformat(row.due) if instant is None else instant.astimezone(zone).date()
            )
            if not today <= day < until or instant is not None and instant < now:
                continue
            record = dict(row._mapping)
            (exams if row.kind == "exam" else assignments).append(
                (
                    (day.isoformat(), instant.timestamp() if instant else float("-inf"), row.id),
                    record,
                )
            )
        budget.check()
        known_effort = [
            record["effort_hours"] for _, record in assignments if record["effort_hours"] > 0
        ]
        return {
            "as_of": now.isoformat().replace("+00:00", "Z"),
            "timezone": zone_name,
            "range_start": today.isoformat(),
            "range_end": until.isoformat(),
            "grades": grades,
            "grades_truncated": len(rows) > 10,
            "upcoming_exams": [record for _, record in sorted(exams)[:5]],
            "exams_total": len(exams),
            "exams_truncated": len(exams) > 5,
            "upcoming_assignments": [record for _, record in sorted(assignments)[:5]],
            "assignments_total": len(assignments),
            "assignments_truncated": len(assignments) > 5,
            "known_effort_hours": round(sum(known_effort), 2) if known_effort else None,
            "unestimated_assignments": len(assignments) - len(known_effort),
        }
