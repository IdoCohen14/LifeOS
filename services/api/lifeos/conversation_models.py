from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class AssistantHistoryPreferences(Base):
    __tablename__ = "assistant_history_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    generation: Mapped[int] = mapped_column(Integer, default=0)


class ConversationTurn(Base):
    __tablename__ = "assistant_conversation_turns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turn_id: Mapped[str] = mapped_column(String(36), unique=True)
    user_text: Mapped[str] = mapped_column(String(1500))
    assistant_text: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[str] = mapped_column(String, index=True)
