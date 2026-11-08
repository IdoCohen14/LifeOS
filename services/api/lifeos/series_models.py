"""Weekly grouping metadata; source events remain ordinary personal records."""

import hashlib
import json

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

FIELDS = ("title", "notes", "start", "end", "all_day")


def event_signature(event):
    values = {key: event[key] if isinstance(event, dict) else getattr(event, key) for key in FIELDS}
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class EventSeries(Base):
    __tablename__ = "event_series"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(240))
    timezone: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[str] = mapped_column(String, index=True)


class SeriesOccurrence(Base):
    __tablename__ = "series_occurrences"
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    series_id: Mapped[str] = mapped_column(
        ForeignKey("event_series.id", ondelete="CASCADE"), index=True
    )
    original_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SeriesDeleteProposal(Base):
    __tablename__ = "series_delete_proposals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_hash: Mapped[str] = mapped_column(
        ForeignKey("sessions.token_hash", ondelete="CASCADE"), index=True
    )
    series_id: Mapped[str] = mapped_column(String)
    payload: Mapped[str] = mapped_column(String)
    expires: Mapped[int] = mapped_column(Integer, index=True)
    deleted_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SeriesRescheduleProposal(Base):
    __tablename__ = "series_reschedule_proposals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_hash: Mapped[str] = mapped_column(
        ForeignKey("sessions.token_hash", ondelete="CASCADE"), index=True
    )
    series_id: Mapped[str] = mapped_column(String)
    payload: Mapped[str] = mapped_column(String)
    expires: Mapped[int] = mapped_column(Integer, index=True)
    changed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
