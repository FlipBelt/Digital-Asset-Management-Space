"""Remote MCP authorization is separate from local device-code grants."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class McpOAuthClient(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mcp_oauth_clients"

    client_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    client_name: Mapped[str] = mapped_column(String(80), nullable=False)
    redirect_uris: Mapped[list] = mapped_column(JSON, nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    grant_types: Mapped[list] = mapped_column(JSON, nullable=False)
    auth_method: Mapped[str] = mapped_column(String(32), nullable=False)
    application_type: Mapped[str | None] = mapped_column(String(16))
    secret_hash: Mapped[str | None] = mapped_column(String(64))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class McpOAuthRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mcp_oauth_requests"

    request_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("mcp_oauth_clients.id"), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    redirect_uri: Mapped[str] = mapped_column(String(2000), nullable=False)
    state: Mapped[str] = mapped_column(String(1024), nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(43), nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    resource: Mapped[str] = mapped_column(String(2000), nullable=False)
    issuer: Mapped[str] = mapped_column(String(2000), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    denied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    code_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class McpOAuthGrant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mcp_oauth_grants"

    client_id: Mapped[UUID] = mapped_column(ForeignKey("mcp_oauth_clients.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    family_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    refresh_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(2000), nullable=False)
    resource: Mapped[str] = mapped_column(String(2000), nullable=False)
    issuer: Mapped[str] = mapped_column(String(2000), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
