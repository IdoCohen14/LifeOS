"""Internal academic roots/read boundaries. Account UI remains disabled."""

import base64
import binascii
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .academic_calendar import slot_occurrences
from .academic_models import (
    AcademicItem,
    Course,
    DocumentSection,
    Grade,
    StudyDocument,
    Term,
    TimetableSlot,
)
from .academic_reads import ReadBudget
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
from .account_records import AccountRecords
from .models import Task


class AccountAcademic(AccountRecords):
    extraction_slots = BoundedSemaphore(2)

    def upload_document(self, account_id, body):
        from .documents import MAX_FILE, DocumentInput, run_extractor, summary

        body = DocumentInput.model_validate(body)
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            if db.scalar(self.query(account_id, Course).where(Course.id == body.course_id)) is None:
                raise LookupError("Academic record not found")
        try:
            content = base64.b64decode(body.content_base64, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Invalid file encoding") from None
        if not content or len(content) > MAX_FILE:
            raise ValueError("File must be between1byte and8MiB")
        if not self.extraction_slots.acquire(blocking=False):
            raise RuntimeError("Document processing busy")
        try:
            result = run_extractor(content, Path(body.filename).suffix.lower())
            if result.returncode:
                raise ValueError("Extraction failed")
            extracted = json.loads(result.stdout.decode("utf-8"))
        except (ValueError, subprocess.TimeoutExpired, OSError):
            raise ValueError("Document could not be extracted") from None
        finally:
            self.extraction_slots.release()
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            if db.scalar(self.query(account_id, Course).where(Course.id == body.course_id)) is None:
                raise LookupError("Academic record not found")
            row = StudyDocument(
                id=str(uuid4()),
                course_id=body.course_id,
                filename=body.filename,
                content=content,
                created_at=datetime.now(timezone.utc).isoformat(),
                text_status=extracted["status"],
            )
            db.add(row)
            db.flush()
            for position, part in enumerate(extracted["sections"]):
                db.add(
                    DocumentSection(
                        id=str(uuid4()),
                        document_id=row.id,
                        reference=part["reference"],
                        position=position,
                        text=part["text"],
                    )
                )
            db.flush()
            result = summary(row)
            db.commit()
            return result

    def search_documents(self, account_id, query, course_id=None):
        if not 1 <= len(query) <= 160:
            raise ValueError("Invalid search length")
        terms = re.findall(r"\w+", query, flags=re.UNICODE)[:12]
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            if not terms:
                return []
            if (
                course_id
                and db.scalar(self.query(account_id, Course).where(Course.id == course_id)) is None
            ):
                raise LookupError("Academic record not found")
            match = " AND ".join('"' + term + '"*' for term in terms)
            rows = db.execute(
                text("""SELECT d.id AS document_id,d.course_id,d.filename,s.reference,
                snippet(document_search,2,'','', ' … ',32) AS excerpt
                FROM document_search JOIN document_sections s ON s.id=document_search.section_id
                JOIN documents d ON d.id=s.document_id JOIN courses c ON c.id=d.course_id
                JOIN terms t ON t.id=c.term_id
                WHERE document_search MATCH :match AND t.account_id=:owner
                AND (:course IS NULL OR d.course_id=:course) ORDER BY rank LIMIT 30"""),
                {"match": match, "owner": account_id, "course": course_id},
            )
            return [dict(row._mapping) for row in rows]

    def list_children(self, account_id, kind):
        model, output = {
            "items": (AcademicItem, ItemOutput),
            "grades": (Grade, GradeOutput),
            "timetable": (TimetableSlot, SlotOutput),
        }[kind]
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            return [
                output.model_validate(row).model_dump(mode="json")
                for row in ReadBudget().collect(
                    db.scalars(self.query(account_id, model).limit(10001)).yield_per(200)
                )
            ]

    def document(self, account_id, document_id, *, download=False):
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            row = db.scalar(
                self.query(account_id, StudyDocument).where(StudyDocument.id == document_id)
            )
            if row is None:
                raise LookupError("Academic record not found")
            if download:
                return row.filename, row.content
            from .documents import summary

            return {
                **summary(row),
                "sections": [
                    {"reference": part.reference, "text": part.text}
                    for part in db.scalars(
                        select(DocumentSection)
                        .where(DocumentSection.document_id == row.id)
                        .order_by(DocumentSection.position)
                    )
                ],
            }

    def delete_academic(self, account_id, kind, record_id):
        model = {
            "terms": Term,
            "courses": Course,
            "items": AcademicItem,
            "grades": Grade,
            "timetable": TimetableSlot,
            "documents": StudyDocument,
        }[kind]
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            row = db.scalar(self.query(account_id, model).where(model.id == record_id))
            if row is None:
                raise LookupError("Academic record not found")
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
                if db.scalar(select(child.id).where(getattr(child, field) == row.id).limit(1)):
                    raise ValueError("Remove associated records first")
            task = row.task if kind == "items" else None
            if task is not None and task.account_id != account_id:
                raise PermissionError("Linked task owner mismatch")
            db.delete(row)
            db.flush()
            if task is not None:
                db.delete(task)
            db.commit()

    def save_child(self, account_id, kind, body, record_id=None):
        model, schema, output = {
            "items": (AcademicItem, ItemInput, ItemOutput),
            "grades": (Grade, GradeInput, GradeOutput),
            "timetable": (TimetableSlot, SlotInput, SlotOutput),
        }[kind]
        body = schema.model_validate(body)
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            row = (
                db.scalar(self.query(account_id, model).where(model.id == record_id))
                if record_id
                else None
            )
            if record_id and row is None:
                raise LookupError("Academic record not found")
            course = db.scalar(self.query(account_id, Course).where(Course.id == body.course_id))
            if course is None:
                raise LookupError("Academic record not found")
            if kind == "timetable":
                slot_occurrences(body, db.get(Term, course.term_id))
            if kind == "grades" and body.weight is not None:
                total = sum(
                    g.weight or 0
                    for g in db.scalars(select(Grade).where(Grade.course_id == course.id))
                    if g.id != record_id
                )
                if total + body.weight > 100.000001:
                    raise ValueError("Grade weights cannot exceed 100%")
            if row is None:
                row = model(id=str(uuid4()))
                db.add(row)
            values = body.model_dump(mode="json")
            if kind == "items":
                completed = values.pop("completed")
                if record_id is None:
                    row.task = Task(
                        id=str(uuid4()),
                        account_id=account_id,
                        created_at=datetime.now(timezone.utc).isoformat(),
                        priority="high" if body.kind == "exam" else "medium",
                    )
                    db.add(row.task)
                elif row.task.account_id != account_id:
                    raise PermissionError("Linked task owner mismatch")
                row.task.title, row.task.notes, row.task.due, row.task.completed = (
                    body.title,
                    body.notes,
                    body.due,
                    completed,
                )
            for key, value in values.items():
                setattr(row, key, value)
            db.flush()
            result = output.model_validate(row).model_dump(mode="json")
            db.commit()
            return result

    def query(self, account_id, model):
        if model is Term:
            return select(Term).where(Term.account_id == account_id)
        if model is Course:
            return select(Course).join(Term).where(Term.account_id == account_id)
        if model is DocumentSection:
            return (
                select(model)
                .join(StudyDocument)
                .join(Course)
                .join(Term)
                .where(Term.account_id == account_id)
            )
        if model in (AcademicItem, Grade, TimetableSlot, StudyDocument):
            return select(model).join(Course).join(Term).where(Term.account_id == account_id)
        raise ValueError("Unsupported academic record")

    def list_roots(self, account_id, kind):
        model, output = {"terms": (Term, TermOutput), "courses": (Course, CourseOutput)}[kind]
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            from .braude_academic import source_state

            managed = source_state(db, account_id).courses
            return [
                {**output.model_validate(row).model_dump(mode="json"),
                 **({"source": "braude", "credits_known": False} if kind == "courses" and row.id in managed else {})}
                for row in ReadBudget().collect(
                    db.scalars(self.query(account_id, model).limit(10001)).yield_per(200)
                )
            ]

    def save_root(self, account_id, kind, body, record_id=None):
        model, schema, output = {
            "terms": (Term, TermInput, TermOutput),
            "courses": (Course, CourseInput, CourseOutput),
        }[kind]
        body = schema.model_validate(body)
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            row = (
                db.scalar(self.query(account_id, model).where(model.id == record_id))
                if record_id
                else None
            )
            if record_id and row is None:
                raise LookupError("Academic record not found")
            if kind == "courses":
                term = db.scalar(self.query(account_id, Term).where(Term.id == body.term_id))
                if term is None:
                    raise LookupError("Academic record not found")
                if row:
                    for slot in db.scalars(
                        select(TimetableSlot).where(TimetableSlot.course_id == row.id)
                    ):
                        slot_occurrences(slot, term)
            elif row:
                for slot in db.scalars(
                    select(TimetableSlot).join(Course).where(Course.term_id == row.id)
                ):
                    slot_occurrences(slot, body)
            if row is None:
                row = model(
                    id=str(uuid4()), **({"account_id": account_id} if model is Term else {})
                )
                db.add(row)
            for key, value in body.model_dump(mode="json").items():
                setattr(row, key, value)
            db.flush()
            result = output.model_validate(row).model_dump(mode="json")
            db.commit()
            return result
