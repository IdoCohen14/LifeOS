from datetime import datetime, timezone
from sqlite3 import SQLITE_BUSY, SQLITE_LOCKED
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .academic_calendar import slot_occurrences
from .academic_models import AcademicItem, Course, Grade, StudyDocument, Term, TimetableSlot
from .academic_reads import read_calendar, read_list
from .academic_schemas import (
    CourseInput,
    CourseOutput,
    GradeInput,
    GradeOutput,
    ItemInput,
    ItemOutput,
    SlotInput,
    SlotOutput,
    TermInput,
    TermOutput,
)
from .models import Task
from .schemas import EventOutput


def begin_academic_write(db):
    try:
        db.execute(text("BEGIN IMMEDIATE"))
    except OperationalError as error:
        code = getattr(error.orig, "sqlite_errorcode", None)
        if isinstance(code, int) and code & 0xFF in (SQLITE_BUSY, SQLITE_LOCKED):
            raise HTTPException(503, "academic_busy", headers={"Retry-After": "1"}) from None
        raise


def academic_router(database, authenticated):
    router = APIRouter(prefix="/academic", dependencies=[Depends(authenticated)])

    def find(db, model, record_id):
        record = db.get(model, record_id)
        if record is None:
            raise HTTPException(404, "Academic record not found")
        return record

    def validate(db, kind, body, record_id=None):
        if kind == "courses":
            term = find(db, Term, body.term_id)
            if record_id:
                for slot in db.scalars(
                    select(TimetableSlot).where(TimetableSlot.course_id == record_id)
                ):
                    slot_occurrences(slot, term)
        elif kind != "terms":
            course = find(db, Course, body.course_id)
            if kind == "timetable":
                slot_occurrences(body, find(db, Term, course.term_id))
            if kind == "grades" and body.weight is not None:
                grades = db.scalars(select(Grade).where(Grade.course_id == course.id)).all()
                total = sum(g.weight or 0 for g in grades if g.id != record_id) + body.weight
                if total > 100.000001:
                    raise ValueError("Grade weights cannot exceed 100%")
        elif record_id:
            slots = db.scalars(
                select(TimetableSlot).join(Course).where(Course.term_id == record_id)
            ).all()
            for slot in slots:
                slot_occurrences(slot, body)

    def save(db, kind, model, body, record_id=None):
        # Validate against the same serialized snapshot that receives the write.
        begin_academic_write(db)
        try:
            validate(db, kind, body, record_id)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        values = body.model_dump(mode="json")
        record = find(db, model, record_id) if record_id else model(id=str(uuid4()))
        if kind == "items":
            completed = values.pop("completed")
            if not record_id:
                task = Task(
                    id=str(uuid4()),
                    created_at=datetime.now(timezone.utc).isoformat(),
                    priority="high" if body.kind == "exam" else "medium",
                )
                record.task = task
                db.add(task)
            record.task.title = body.title
            record.task.notes = body.notes
            record.task.due = body.due
            record.task.completed = completed
        for field, value in values.items():
            setattr(record, field, value)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def remove(db, kind, model, record_id):
        begin_academic_write(db)
        record = find(db, model, record_id)
        children = {
            "terms": [(Course, "term_id")],
            "courses": [
                (AcademicItem, "course_id"),
                (TimetableSlot, "course_id"),
                (Grade, "course_id"),
                (StudyDocument, "course_id"),
            ],
        }.get(kind, [])
        for child, field in children:
            if db.scalar(select(child.id).where(getattr(child, field) == record_id).limit(1)):
                raise HTTPException(
                    409, "Remove the associated records before deleting this course or term"
                )
        task = record.task if kind == "items" else None
        db.delete(record)
        db.flush()
        if task:
            db.delete(task)
        db.commit()

    def register(kind, model, input_schema, output_schema):
        def listing(db: Session = Depends(database)):
            return read_list(db, model)

        def create(body: input_schema, db: Session = Depends(database)):
            return save(db, kind, model, body)

        def update(record_id: str, body: input_schema, db: Session = Depends(database)):
            return save(db, kind, model, body, record_id)

        def destroy(record_id: str, db: Session = Depends(database)):
            remove(db, kind, model, record_id)

        router.add_api_route(
            f"/{kind}",
            listing,
            methods=["GET"],
            response_model=list[output_schema],
            name=f"list_{kind}",
        )
        router.add_api_route(
            f"/{kind}",
            create,
            methods=["POST"],
            response_model=output_schema,
            status_code=201,
            name=f"create_{kind}",
        )
        router.add_api_route(
            f"/{kind}/{{record_id}}",
            update,
            methods=["PUT"],
            response_model=output_schema,
            name=f"update_{kind}",
        )
        router.add_api_route(
            f"/{kind}/{{record_id}}",
            destroy,
            methods=["DELETE"],
            status_code=204,
            name=f"delete_{kind}",
        )

    for args in [
        ("terms", Term, TermInput, TermOutput),
        ("courses", Course, CourseInput, CourseOutput),
        ("items", AcademicItem, ItemInput, ItemOutput),
        ("timetable", TimetableSlot, SlotInput, SlotOutput),
        ("grades", Grade, GradeInput, GradeOutput),
    ]:
        register(*args)

    @router.get("/calendar", response_model=list[EventOutput])
    def calendar(db: Session = Depends(database)):
        return read_calendar(db)

    return router
