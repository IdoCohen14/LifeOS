import base64
import binascii
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .academic_models import Course, DocumentSection, StudyDocument

MAX_FILE = 8 * 1024 * 1024
EXTRACTOR_SCRIPT = Path(__file__).with_name("document_extract.py")


def run_extractor(content, suffix, *, timeout=12):
    return subprocess.run(
        [sys.executable, str(EXTRACTOR_SCRIPT), suffix],
        input=content,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


class DocumentInput(BaseModel):
    course_id: str
    filename: str = Field(min_length=1, max_length=240)
    content_base64: str = Field(max_length=11184812)

    @field_validator("filename")
    @classmethod
    def safe_filename(cls, value):
        if any(c in value for c in ("/", "\\")) or any(ord(c) < 32 for c in value):
            raise ValueError("Filename must not contain paths or control characters")
        if Path(value).suffix.lower() not in (".pdf", ".docx", ".pptx", ".txt", ".md"):
            raise ValueError("Unsupported file type")
        return value


def summary(document):
    return {
        "id": document.id,
        "course_id": document.course_id,
        "filename": document.filename,
        "size": len(document.content),
        "created_at": document.created_at,
        "text_status": document.text_status,
    }


def documents_router(database, authenticated):
    router = APIRouter(prefix="/academic/documents", dependencies=[Depends(authenticated)])
    extraction_slots = BoundedSemaphore(2)

    def find(db, record_id):
        document = db.get(StudyDocument, record_id)
        if document is None:
            raise HTTPException(404, "Document not found")
        return document

    @router.get("")
    def listing(db: Session = Depends(database)):
        # Avoid loading private BLOBs for the list endpoint.
        from sqlalchemy import func

        rows = db.execute(
            select(
                StudyDocument.id,
                StudyDocument.course_id,
                StudyDocument.filename,
                func.length(StudyDocument.content).label("size"),
                StudyDocument.created_at,
                StudyDocument.text_status,
            )
        )
        return [dict(row._mapping) for row in rows]

    @router.post("", status_code=201)
    def upload(body: DocumentInput, db: Session = Depends(database)):
        if db.get(Course, body.course_id) is None:
            raise HTTPException(404, "Course not found")
        try:
            content = base64.b64decode(body.content_base64, validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(422, "Invalid file encoding") from None
        if not content or len(content) > MAX_FILE:
            raise HTTPException(413, "File must be between 1 byte and 8 MiB")
        if not extraction_slots.acquire(blocking=False):
            raise HTTPException(
                429, "Document processing is busy; retry shortly", headers={"Retry-After": "1"}
            )
        try:
            result = run_extractor(content, Path(body.filename).suffix.lower())
            if result.returncode:
                raise ValueError()
            extracted = json.loads(result.stdout.decode("utf-8"))
        except (ValueError, subprocess.TimeoutExpired, OSError):
            raise HTTPException(
                422,
                "Could not extract file: check format, encryption and size; scanned PDFs require OCR",
            ) from None
        finally:
            extraction_slots.release()
        document = StudyDocument(
            id=str(uuid4()),
            course_id=body.course_id,
            filename=body.filename,
            content=content,
            created_at=datetime.now(timezone.utc).isoformat(),
            text_status=extracted["status"],
        )
        db.add(document)
        db.flush()
        for position, section in enumerate(extracted["sections"]):
            db.add(
                DocumentSection(
                    id=str(uuid4()),
                    document_id=document.id,
                    reference=section["reference"],
                    position=position,
                    text=section["text"],
                )
            )
        db.commit()
        return summary(document)

    @router.get("/search")
    def search(
        q: str = Query(min_length=1, max_length=160),
        course_id: str | None = None,
        db: Session = Depends(database),
    ):
        terms = re.findall(r"\w+", q, flags=re.UNICODE)[:12]
        if not terms:
            return []
        match = " AND ".join('"' + term + '"*' for term in terms)
        rows = db.execute(
            text("""SELECT d.id AS document_id,d.course_id,d.filename,s.reference,
            snippet(document_search,2,'','', ' … ',32) AS excerpt
            FROM document_search JOIN document_sections s ON s.id=document_search.section_id
            JOIN documents d ON d.id=s.document_id
            WHERE document_search MATCH :match AND (:course IS NULL OR d.course_id=:course)
            ORDER BY rank LIMIT 30"""),
            {"match": match, "course": course_id},
        )
        return [dict(row._mapping) for row in rows]

    @router.get("/{record_id}")
    def detail(record_id: str, db: Session = Depends(database)):
        document = find(db, record_id)
        sections = db.scalars(
            select(DocumentSection)
            .where(DocumentSection.document_id == record_id)
            .order_by(DocumentSection.position)
        ).all()
        return {
            **summary(document),
            "sections": [
                {"reference": section.reference, "text": section.text} for section in sections
            ],
        }

    @router.get("/{record_id}/download")
    def download(record_id: str, db: Session = Depends(database)):
        document = find(db, record_id)
        return Response(
            document.content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.filename, safe='')}"
            },
        )

    @router.delete("/{record_id}", status_code=204)
    def destroy(record_id: str, db: Session = Depends(database)):
        db.delete(find(db, record_id))
        db.commit()

    return router
