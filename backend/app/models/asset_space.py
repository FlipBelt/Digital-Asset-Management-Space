"""Personal facts attached to the canonical asset and subscription registry."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import ArchiveMixin, Base, TimestampMixin, UUIDPrimaryKeyMixin


class AssetBookmark(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asset_bookmarks"
    __table_args__ = (UniqueConstraint("person_id", "asset_id"),)

    person_id: Mapped[UUID] = mapped_column(ForeignKey("people.id"), nullable=False)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)


class AssetEvidence(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "asset_evidence"

    person_id: Mapped[UUID] = mapped_column(ForeignKey("people.id"), nullable=False, index=True)
    asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    subscription_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("service_instances.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str] = mapped_column(Text, nullable=False)
    observed_effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(32), default="pending_review", server_default="pending_review", nullable=False
    )
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class AssetConfirmation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asset_confirmations"

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    asset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    result_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sharing_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
