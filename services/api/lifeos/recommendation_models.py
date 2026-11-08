from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class RecommendationDismissal(Base):
    __tablename__ = "recommendation_dismissals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    expires: Mapped[int] = mapped_column(Integer, index=True)
