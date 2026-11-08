from sqlalchemy import Boolean, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class GoogleConnection(Base):
    __tablename__ = "google_connection"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    credentials: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    state: Mapped[str] = mapped_column(String, default="disconnected")
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    last_success: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_sync: Mapped[int] = mapped_column(Integer, default=0)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_until: Mapped[int] = mapped_column(Integer, default=0)


class GoogleOAuthState(Base):
    __tablename__ = "google_oauth_states"
    state_hash: Mapped[str] = mapped_column(String, primary_key=True)
    session_hash: Mapped[str] = mapped_column(ForeignKey("sessions.token_hash", ondelete="CASCADE"))
    verifier: Mapped[bytes] = mapped_column(LargeBinary)
    redirect_uri: Mapped[str] = mapped_column(String)
    expires: Mapped[int] = mapped_column(Integer)


class GoogleCalendar(Base):
    __tablename__ = "google_calendars"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    timezone: Mapped[str] = mapped_column(String)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_token: Mapped[str | None] = mapped_column(String, nullable=True)


class GoogleRecord(Base):
    __tablename__ = "google_records"
    calendar_id: Mapped[str] = mapped_column(
        ForeignKey("google_calendars.id", ondelete="CASCADE"), primary_key=True
    )
    external_id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
