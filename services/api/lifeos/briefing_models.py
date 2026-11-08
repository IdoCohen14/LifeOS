from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class BriefingSchedule(Base):
    __tablename__ = "briefing_schedule"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_time: Mapped[str] = mapped_column(String(5), default="08:00")
    weekly_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    weekly_day: Mapped[int] = mapped_column(Integer, default=6)
    weekly_time: Mapped[str] = mapped_column(String(5), default="08:00")
    last_run: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)


class ScheduledBriefing(Base):
    __tablename__ = "scheduled_briefings"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    period_start: Mapped[str] = mapped_column(String(10), index=True)
    timezone: Mapped[str] = mapped_column(String)
    generated_at: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[str] = mapped_column(Text)
