"""Session-bound, reviewed, atomic manual course entry. No provider or model calls."""

import json
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ForeignKey, Integer, String, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from .academic import begin_academic_write
from .academic_models import Course, Term
from .academic_schemas import CourseFields
from .db import Base


class CourseBatch(Base):
    __tablename__ = "course_batches"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_hash: Mapped[str] = mapped_column(
        ForeignKey("sessions.token_hash", ondelete="CASCADE"), index=True
    )
    payload: Mapped[str] = mapped_column(String)
    expires: Mapped[int] = mapped_column(Integer)
    result: Mapped[str | None] = mapped_column(String, nullable=True)


class Row(CourseFields):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class BatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    term_id: str = Field(min_length=1, max_length=100)
    rows: list[Row] = Field(min_length=1, max_length=20)


def term_value(term):
    if term is None:
        raise HTTPException(409, "course_batch_changed")
    return {key: getattr(term, key) for key in ("id", "name", "start_date", "end_date")}


def check_courses(db, term_id, rows):
    names, codes = set(), set()
    for row in rows:
        name, code = row["name"].casefold(), row["code"].casefold()
        if name in names or code and code in codes:
            raise HTTPException(422, "course_batch_duplicate")
        names.add(name)
        if code:
            codes.add(code)
    for index, (name, code) in enumerate(
        db.execute(select(Course.name, Course.code).where(Course.term_id == term_id)).yield_per(128)
    ):
        if index >= 10000:
            raise HTTPException(503, "course_batch_limit")
        if name.strip().casefold() in names or code and code.strip().casefold() in codes:
            raise HTTPException(409, "course_batch_duplicate")


def create_preview(db, session, payload):
    db.execute(
        delete(CourseBatch).where(
            CourseBatch.session_hash == session.token_hash, CourseBatch.expires <= time.time()
        )
    )
    count = db.scalar(
        select(func.count())
        .select_from(CourseBatch)
        .where(CourseBatch.session_hash == session.token_hash, CourseBatch.result.is_(None))
    )
    if count >= 20:
        raise HTTPException(429, "academic_batch_limit")
    id = str(uuid4())
    db.add(
        CourseBatch(
            id=id,
            session_hash=session.token_hash,
            payload=json.dumps(payload),
            expires=int(time.time()) + 900,
        )
    )
    from .assistant import session_scope

    session_scope(db, session.token_hash, session.account_id)
    db.commit()
    return {"id": id, **payload}


def find_receipt(db, id, session, kind):
    batch = db.get(CourseBatch, id)
    if (
        not batch
        or batch.session_hash != session.token_hash
        or batch.expires <= time.time()
        or json.loads(batch.payload).get("kind", "courses") != kind
    ):
        raise HTTPException(404, "academic_batch_expired")
    return batch


def course_batch_router(database, authenticated):
    router = APIRouter(prefix="/academic/course-batches", dependencies=[Depends(authenticated)])

    @router.post("/preview")
    def preview(body: BatchInput, db=Depends(database), session=Depends(authenticated)):
        begin_academic_write(db)
        term = term_value(db.get(Term, body.term_id))
        rows = [row.model_dump() for row in body.rows]
        check_courses(db, body.term_id, rows)
        return create_preview(db, session, {"kind": "courses", "term": term, "rows": rows})

    def find(db, id, session):
        return find_receipt(db, id, session, "courses")

    @router.post("/{id}/confirm")
    def confirm(id: str, db=Depends(database), session=Depends(authenticated)):
        begin_academic_write(db)
        batch = find(db, id, session)
        if batch.result:
            return json.loads(batch.result)
        payload = json.loads(batch.payload)
        term = payload["term"]
        if term_value(db.get(Term, term["id"])) != term:
            raise HTTPException(409, "course_batch_changed")
        rows = payload["rows"]
        check_courses(db, term["id"], rows)
        ids = []
        for row in rows:
            course = Course(id=str(uuid4()), term_id=term["id"], **row)
            db.add(course)
            ids.append(course.id)
        result = {"ids": ids, "created_count": len(ids)}
        batch.result = json.dumps(result)
        db.flush()
        if session.expires <= time.time() or batch.expires <= time.time():
            raise HTTPException(409, "course_batch_expired")
        db.commit()
        return result

    @router.delete("/{id}", status_code=204)
    def cancel(id: str, db=Depends(database), session=Depends(authenticated)):
        begin_academic_write(db)
        batch = find(db, id, session)
        if batch.result:
            raise HTTPException(409, "course_batch_confirmed")
        db.delete(batch)
        db.commit()

    return router
