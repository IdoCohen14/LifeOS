from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class NotificationPreferences(Base):
    __tablename__ = "notification_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    tasks: Mapped[bool] = mapped_column(Boolean, default=True)
    conflicts: Mapped[bool] = mapped_column(Boolean, default=True)
    events: Mapped[bool] = mapped_column(Boolean, default=False)
    mail: Mapped[bool] = mapped_column(Boolean, default=False)
    briefings: Mapped[bool] = mapped_column(Boolean, default=True)
    quiet_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    quiet_start: Mapped[str] = mapped_column(String(5), default="22:00")
    quiet_end: Mapped[str] = mapped_column(String(5), default="07:00")


class NotificationRead(Base):
    __tablename__ = "notification_reads"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    read_at: Mapped[int] = mapped_column(Integer, index=True)


class NotificationAction(Base):
    __tablename__ = "notification_actions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    snoozed_until: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[int] = mapped_column(Integer, index=True)
