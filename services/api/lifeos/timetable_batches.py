"""Reviewed multi-weekday manual timetable entry using academic batch receipts."""

import json
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ConfigDict, Field, StrictInt, field_validator
from sqlalchemy import select

from .academic import begin_academic_write
from .academic_calendar import slot_occurrences
from .academic_models import Course, Term, TimetableSlot
from .academic_schemas import SlotFields, SlotInput
from .course_batches import create_preview, find_receipt, term_value


class TimetableInput(SlotFields):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    weekdays: list[StrictInt] = Field(min_length=1, max_length=7)

    @field_validator("weekdays")
    @classmethod
    def valid_days(cls, value):
        if len(set(value)) != len(value) or any(day < 0 or day > 6 for day in value):
            raise ValueError("Choose distinct weekdays 0 through 6")
        return sorted(value)


def source(db, course_id):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(409, "timetable_batch_changed")
    return {"id": course.id, "name": course.name, "term_id": course.term_id}, term_value(
        db.get(Term, course.term_id)
    )


def validate_rows(db, rows, term):
    from types import SimpleNamespace

    keys = {(row["weekday"], row["start_time"], row["end_time"], row["timezone"]) for row in rows}
    for row in rows:
        try:
            slot_occurrences(SlotInput.model_validate(row), SimpleNamespace(**term))
        except ValueError:
            raise HTTPException(422, "timetable_batch_time") from None
    for index, slot in enumerate(
        db.scalars(
            select(TimetableSlot).where(TimetableSlot.course_id == rows[0]["course_id"])
        ).yield_per(128)
    ):
        if index >= 10000:
            raise HTTPException(503, "timetable_batch_limit")
        if (slot.weekday, slot.start_time, slot.end_time, slot.timezone) in keys:
            raise HTTPException(409, "timetable_batch_duplicate")


def timetable_batch_router(database, authenticated):
    router = APIRouter(prefix="/academic/timetable-batches", dependencies=[Depends(authenticated)])

    @router.post("/preview")
    def preview(body: TimetableInput, db=Depends(database), session=Depends(authenticated)):
        begin_academic_write(db)
        course, term = source(db, body.course_id)
        fields = body.model_dump(exclude={"weekdays"})
        rows = [{**fields, "weekday": day} for day in body.weekdays]
        validate_rows(db, rows, term)
        return create_preview(
            db, session, {"kind": "timetable", "course": course, "term": term, "rows": rows}
        )

    @router.post("/{id}/confirm")
    def confirm(id: str, db=Depends(database), session=Depends(authenticated)):
        begin_academic_write(db)
        batch = find_receipt(db, id, session, "timetable")
        if batch.result:
            return json.loads(batch.result)
        payload = json.loads(batch.payload)
        course, term = source(db, payload["course"]["id"])
        if course != payload["course"] or term != payload["term"]:
            raise HTTPException(409, "timetable_batch_changed")
        validate_rows(db, payload["rows"], term)
        ids = []
        for row in payload["rows"]:
            id = str(uuid4())
            db.add(TimetableSlot(id=id, **row))
            ids.append(id)
        result = {"ids": ids, "created_count": len(ids)}
        batch.result = json.dumps(result)
        db.flush()
        if session.expires <= time.time() or batch.expires <= time.time():
            raise HTTPException(409, "timetable_batch_expired")
        db.commit()
        return result

    @router.delete("/{id}", status_code=204)
    def cancel(id: str, db=Depends(database), session=Depends(authenticated)):
        begin_academic_write(db)
        batch = find_receipt(db, id, session, "timetable")
        if batch.result:
            raise HTTPException(409, "timetable_batch_confirmed")
        db.delete(batch)
        db.commit()

    return router
