from sqlalchemy import Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Term(Base):
    __tablename__ = "terms"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[str] = mapped_column(String)
    end_date: Mapped[str] = mapped_column(String)


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    term_id: Mapped[str] = mapped_column(ForeignKey("terms.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(50), default="")
    instructor: Mapped[str] = mapped_column(String(120), default="")
    credits: Mapped[float] = mapped_column(Float, default=0)
    color: Mapped[str] = mapped_column(String(7), default="#a597ff")


class AcademicItem(Base):
    __tablename__ = "academic_items"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), unique=True)
    title: Mapped[str] = mapped_column(String(240))
    notes: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20))
    due: Mapped[str] = mapped_column(String, index=True)
    effort_hours: Mapped[float] = mapped_column(Float, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=120)
    task: Mapped["Task"] = relationship(back_populates="academic_item")  # noqa: F821
    course: Mapped["Course"] = relationship()

    @property
    def completed(self):
        return self.task.completed


class TimetableSlot(Base):
    __tablename__ = "timetable"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[str] = mapped_column(String(5))
    end_time: Mapped[str] = mapped_column(String(5))
    timezone: Mapped[str] = mapped_column(String(80))
    location: Mapped[str] = mapped_column(String(240), default="")


class Grade(Base):
    __tablename__ = "grades"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    score: Mapped[float] = mapped_column(Float)
    maximum: Mapped[float] = mapped_column(Float)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)


class StudyDocument(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    filename: Mapped[str] = mapped_column(String(240))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[str] = mapped_column(String)
    text_status: Mapped[str] = mapped_column(String(30))


class DocumentSection(Base):
    __tablename__ = "document_sections"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    reference: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
