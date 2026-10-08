"""Delegated agent access and structured incubation records, separate from Assets."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class AgentGrant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_grants"

    device_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    client_name: Mapped[str] = mapped_column(String(80), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    device_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentOperation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_operations"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)


class AgentIncubation(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "agent_incubations"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    workflow_summary: Mapped[str] = mapped_column(Text, nullable=False)
    opportunity_summary: Mapped[str] = mapped_column(Text, nullable=False)
    blueprint_summary: Mapped[str] = mapped_column(Text, nullable=False)
    next_step: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id"))
