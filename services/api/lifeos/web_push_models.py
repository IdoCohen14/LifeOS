from sqlalchemy import Boolean, Float, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class PushConfig(Base):
    __tablename__ = "push_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_key: Mapped[str] = mapped_column(String)
    private_key: Mapped[bytes] = mapped_column(LargeBinary)
    contact: Mapped[str] = mapped_column(String(254))
    revision: Mapped[int] = mapped_column(Integer)


class PushDevice(Base):
    __tablename__ = "push_devices"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    endpoint_hash: Mapped[str] = mapped_column(String(64), unique=True)
    subscription: Mapped[bytes] = mapped_column(LargeBinary)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    generation: Mapped[int] = mapped_column(Integer, default=1)
    last_seen: Mapped[float] = mapped_column(Float)
    cooldown_until: Mapped[float] = mapped_column(Float, default=0)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)


class PushDelivery(Base):
    __tablename__ = "push_deliveries"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("push_devices.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[float] = mapped_column(Float, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt: Mapped[float] = mapped_column(Float, default=0)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)


class AccountPushConfig(Base):
    __tablename__ = "account_push_config"
    id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    public_key: Mapped[str] = mapped_column(String)
    private_key: Mapped[bytes] = mapped_column(LargeBinary)
    contact: Mapped[str] = mapped_column(String(254))
    revision: Mapped[int] = mapped_column(Integer)


class AccountPushDevice(Base):
    __tablename__ = "account_push_devices"
    __table_args__ = (UniqueConstraint("account_id", "endpoint_hash"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    endpoint_hash: Mapped[str] = mapped_column(String(64))
    subscription: Mapped[bytes] = mapped_column(LargeBinary)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    generation: Mapped[int] = mapped_column(Integer, default=1)
    last_seen: Mapped[float] = mapped_column(Float)
    cooldown_until: Mapped[float] = mapped_column(Float, default=0)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)


class AccountPushDelivery(Base):
    __tablename__ = "account_push_deliveries"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("account_push_devices.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[float] = mapped_column(Float, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt: Mapped[float] = mapped_column(Float, default=0)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
