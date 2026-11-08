from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class AssistantProposal(Base):
    __tablename__ = "assistant_proposals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_hash: Mapped[str] = mapped_column(
        ForeignKey("sessions.token_hash", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String)
    payload: Mapped[str] = mapped_column(String)
    expires: Mapped[int] = mapped_column(Integer)
    confirmed_id: Mapped[str | None] = mapped_column(String, nullable=True)
