from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class MoodleConnection(Base):
    __tablename__ = "moodle_connection"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    credentials: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    state: Mapped[str] = mapped_column(String, default="disconnected")
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    last_success: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_sync: Mapped[int] = mapped_column(Integer, default=0)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_until: Mapped[int] = mapped_column(Integer, default=0)


class MoodleEvent(Base):
    __tablename__ = "moodle_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[str] = mapped_column(String)
