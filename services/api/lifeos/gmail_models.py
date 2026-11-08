from sqlalchemy import ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class GmailConnection(Base):
    __tablename__ = "gmail_connection"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    credentials: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    state: Mapped[str] = mapped_column(String, default="disconnected")
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    last_success: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_sync: Mapped[int] = mapped_column(Integer, default=0)
    history_id: Mapped[str | None] = mapped_column(String, nullable=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_until: Mapped[int] = mapped_column(Integer, default=0)


class GmailOAuthState(Base):
    __tablename__ = "gmail_oauth_states"
    state_hash: Mapped[str] = mapped_column(String, primary_key=True)
    session_hash: Mapped[str] = mapped_column(ForeignKey("sessions.token_hash", ondelete="CASCADE"))
    verifier: Mapped[bytes] = mapped_column(LargeBinary)
    redirect_uri: Mapped[str] = mapped_column(String)
    expires: Mapped[int] = mapped_column(Integer)


class GmailMessage(Base):
    __tablename__ = "gmail_messages"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[str] = mapped_column(String)


class GmailReviewed(Base):
    __tablename__ = "gmail_reviewed"
    id: Mapped[str] = mapped_column(String, primary_key=True)
