from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def local_utc(day: date, clock: str, zone: str) -> str:
    naive = datetime.fromisoformat(f"{day.isoformat()}T{clock}")
    zone_info = ZoneInfo(zone)
    value = naive.replace(tzinfo=zone_info, fold=0)
    if (
        value.astimezone(timezone.utc).astimezone(zone_info).replace(tzinfo=None) != naive
        or value.utcoffset() != naive.replace(tzinfo=zone_info, fold=1).utcoffset()
    ):
        raise ValueError("Timetable includes a missing or ambiguous local time during DST")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def iter_slot_occurrences(slot, term, budget=None):
    start = date.fromisoformat(str(term.start_date))
    end = date.fromisoformat(str(term.end_date))
    day = start + timedelta(days=(slot.weekday - (start.weekday() + 1) % 7) % 7)
    while day <= end:
        if budget:
            budget()
        yield (
            day,
            local_utc(day, slot.start_time, slot.timezone),
            local_utc(day, slot.end_time, slot.timezone),
        )
        day += timedelta(days=7)


def slot_occurrences(slot, term):
    return list(iter_slot_occurrences(slot, term))


def iter_calendar(db, budget=None, *, account_id=None):
    from sqlalchemy import select

    from .academic_models import AcademicItem, Course, Term, TimetableSlot

    for slot, course, term in db.execute(
        select(TimetableSlot, Course, Term)
        .join(Course, TimetableSlot.course_id == Course.id)
        .join(Term, Course.term_id == Term.id)
        .where(Term.account_id == account_id)
        .execution_options(yield_per=200)
    ):
        if budget:
            budget()
        for day, start, end in iter_slot_occurrences(slot, term, budget):
            yield (
                {
                    "id": f"slot-{slot.id}-{day}",
                    "title": course.name,
                    "notes": slot.location,
                    "start": start,
                    "end": end,
                    "all_day": False,
                    "created_at": "1970-01-01T00:00:00Z",
                    "source": "timetable",
                    "course_id": course.id,
                    "academic_id": slot.id,
                }
            )
    for item, course in db.execute(
        select(AcademicItem, Course)
        .join(Course, AcademicItem.course_id == Course.id)
        .join(Term, Course.term_id == Term.id)
        .where(Term.account_id == account_id)
        .execution_options(yield_per=200)
    ):
        if budget:
            budget()
        if item.kind == "assignment" and item.completed:
            continue
        all_day = len(item.due) == 10
        end = (
            (date.fromisoformat(item.due) + timedelta(days=1)).isoformat()
            if all_day
            else (
                datetime.fromisoformat(item.due)
                + timedelta(minutes=item.duration_minutes if item.kind == "exam" else 1)
            )
            .isoformat()
            .replace("+00:00", "Z")
        )
        yield (
            {
                "id": f"item-{item.id}",
                "title": f"{course.name}: {item.title}",
                "notes": item.notes,
                "start": item.due,
                "end": end,
                "all_day": all_day,
                "created_at": item.task.created_at,
                "source": item.kind,
                "course_id": course.id,
                "academic_id": item.id,
            }
        )


def project_calendar(db):
    return sorted(iter_calendar(db), key=lambda event: event["start"])
