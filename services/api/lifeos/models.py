from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, ForeignKeyConstraint, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

if TYPE_CHECKING:
    from .academic_models import AcademicItem


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(240))
    notes: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(10), index=True)
    due: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[str] = mapped_column(String)
    academic_item: Mapped["AcademicItem | None"] = relationship(
        back_populates="task", uselist=False
    )

    @property
    def academic_id(self):
        return self.academic_item.id if self.academic_item else None

    @property
    def academic_course_id(self):
        return self.academic_item.course_id if self.academic_item else None

    @property
    def academic_kind(self):
        return self.academic_item.kind if self.academic_item else None

    @property
    def academic_course_name(self):
        return self.academic_item.course.name if self.academic_item else None


class CalendarEvent(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(240))
    notes: Mapped[str] = mapped_column(Text, default="")
    start: Mapped[str] = mapped_column(String, index=True)
    end: Mapped[str] = mapped_column(String, index=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String)


class Settings(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    display_name: Mapped[str] = mapped_column(String(80), default="")
    language: Mapped[str] = mapped_column(String(2), default="he")
    theme: Mapped[str] = mapped_column(String(10), default="dark")
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Jerusalem")


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    login: Mapped[str] = mapped_column(String(254), unique=True)
    password_digest: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AccountPreference(Base):
    __tablename__ = "account_preferences"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[str] = mapped_column(Text)


class AccountLifecycle(Base):
    __tablename__ = "account_lifecycle"
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    recovery_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deletion_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    deletion_state: Mapped[str | None] = mapped_column(String(24), nullable=True)


class AccountProvider(Base):
    __tablename__ = "account_providers"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    credentials: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_until: Mapped[int] = mapped_column(Integer, default=0)
    last_success: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    next_sync: Mapped[int] = mapped_column(Integer, default=0)
    authorized: Mapped[bool] = mapped_column(Boolean, default=False)


class AccountProviderRecord(Base):
    __tablename__ = "account_provider_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "provider"],
            ["account_providers.account_id", "account_providers.provider"],
            ondelete="CASCADE",
        ),
    )
    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)


class AccountOAuthState(Base):
    __tablename__ = "account_oauth_states"
    state_hash: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    session_hash: Mapped[str] = mapped_column(ForeignKey("sessions.token_hash", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer)
    verifier: Mapped[bytes] = mapped_column(LargeBinary)
    redirect_uri: Mapped[str] = mapped_column(String)
    expires: Mapped[int] = mapped_column(Integer, index=True)


class AccountMailReview(Base):
    __tablename__ = "account_mail_reviews"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    provider_revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(256), primary_key=True)


class AccountConversationTurn(Base):
    __tablename__ = "account_conversation_turns"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    user_text: Mapped[str] = mapped_column(Text)
    reply_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, index=True)
    include_context: Mapped[bool] = mapped_column(Boolean, default=True)


class AccountNoticeState(Base):
    __tablename__ = "account_notice_states"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    read_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    snoozed_until: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommendation_until: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[int] = mapped_column(Integer)


class AccountMoodleChange(Base):
    __tablename__ = "account_moodle_changes"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(16))
    previous: Mapped[str | None] = mapped_column(Text, nullable=True)
    current: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[int] = mapped_column(Integer, index=True)


class AccountBriefing(Base):
    __tablename__ = "account_briefings"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    period_start: Mapped[str] = mapped_column(String(10))
    timezone: Mapped[str] = mapped_column(String(80))
    generated_at: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[str] = mapped_column(Text)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    csrf: Mapped[str] = mapped_column(String)
    expires: Mapped[int] = mapped_column(Integer, index=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
