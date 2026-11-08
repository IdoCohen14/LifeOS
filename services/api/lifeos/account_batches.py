"""Owned reviewed bulk course and multi-day timetable capture."""

import json
import time
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .academic_models import Course, Term, TimetableSlot
from .account_academic import AccountAcademic
from .accounts import require_account_session
from .assistant import session_scope
from .course_batches import BatchInput, check_courses, create_preview, find_receipt, term_value
from .timetable_batches import TimetableInput, validate_rows


class AccountBatches(AccountAcademic):
    def parents(self, db, account_id, kind, id):
        if kind == "courses":
            return {
                "term": term_value(db.scalar(self.query(account_id, Term).where(Term.id == id)))
            }
        course = db.scalar(self.query(account_id, Course).where(Course.id == id))
        if not course:
            raise HTTPException(409, "timetable_batch_changed")
        return {
            "course": {"id": course.id, "name": course.name, "term_id": course.term_id},
            "term": term_value(
                db.scalar(self.query(account_id, Term).where(Term.id == course.term_id))
            ),
        }

    def preview(self, account_id, token, kind, values):
        schema = {"courses": BatchInput, "timetable": TimetableInput}[kind]
        body = schema.model_validate(values)
        with Session(self.engine) as db:
            begin_academic_write(db)
            session = require_account_session(db, account_id, token)
            parents = self.parents(
                db, account_id, kind, body.term_id if kind == "courses" else body.course_id
            )
            if kind == "courses":
                rows = [row.model_dump() for row in body.rows]
                check_courses(db, body.term_id, rows)
            else:
                fields = body.model_dump(exclude={"weekdays"})
                rows = [{**fields, "weekday": day} for day in body.weekdays]
                validate_rows(db, rows, parents["term"])
            return create_preview(db, session, {"kind": kind, **parents, "rows": rows})

    def confirm(self, account_id, token, kind, id):
        if kind not in ("courses", "timetable"):
            raise ValueError("Invalid batch kind")
        with Session(self.engine) as db:
            begin_academic_write(db)
            session = require_account_session(db, account_id, token)
            receipt = find_receipt(db, id, session, kind)
            if receipt.result:
                return json.loads(receipt.result)
            payload = json.loads(receipt.payload)
            source_id = payload["term"]["id"] if kind == "courses" else payload["course"]["id"]
            parents = self.parents(db, account_id, kind, source_id)
            if any(payload[key] != value for key, value in parents.items()):
                raise ValueError("Academic batch changed")
            rows = payload["rows"]
            if kind == "courses":
                check_courses(db, parents["term"]["id"], rows)
            else:
                validate_rows(db, rows, parents["term"])
            ids = []
            for values in rows:
                id = str(uuid4())
                db.add(
                    Course(id=id, term_id=parents["term"]["id"], **values)
                    if kind == "courses"
                    else TimetableSlot(id=id, **values)
                )
                ids.append(id)
            result = {"ids": ids, "created_count": len(ids)}
            receipt.result = json.dumps(result)
            db.flush()
            session_scope(db, session.token_hash, account_id)
            if receipt.expires <= time.time():
                raise ValueError("Academic batch expired")
            db.commit()
            return result

    def cancel(self, account_id, token, kind, id):
        with Session(self.engine) as db:
            begin_academic_write(db)
            session = require_account_session(db, account_id, token)
            receipt = find_receipt(db, id, session, kind)
            if receipt.result:
                raise ValueError("Academic batch confirmed")
            db.delete(receipt)
            db.commit()
