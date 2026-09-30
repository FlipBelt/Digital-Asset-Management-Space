from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DingTalkWebLoginState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Short-lived browser-bound OAuth challenge; never stores an auth code or token."""

    __tablename__ = "dingtalk_web_login_states"
    __table_args__ = (Index("ix_dingtalk_web_login_states_expires_at", "expires_at"),)

    state_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    browser_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    return_path: Mapped[str] = mapped_column(String(2000), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
