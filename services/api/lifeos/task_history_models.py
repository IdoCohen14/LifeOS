from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class TaskStatusHistory(Base):
    __tablename__ = "task_status_history"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    completed: Mapped[bool] = mapped_column(Boolean)
    occurred_at: Mapped[str] = mapped_column(String, index=True)


class TaskHistoryMetadata(Base):
    __tablename__ = "task_history_metadata"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracking_started_at: Mapped[str] = mapped_column(String)
