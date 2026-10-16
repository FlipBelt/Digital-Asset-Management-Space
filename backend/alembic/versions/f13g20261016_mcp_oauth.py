"""Add isolated remote MCP OAuth clients, requests and rotating grants."""

import sqlalchemy as sa

from alembic import op

revision = "f13g20261016"
down_revision = "f13f20261010"
branch_labels = None
depends_on = None


def common():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade():
    op.create_table(
        "mcp_oauth_clients",
        *common(),
        sa.Column("client_id", sa.String(80), unique=True, nullable=False),
        sa.Column("client_name", sa.String(80), nullable=False),
        sa.Column("redirect_uris", sa.JSON(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("grant_types", sa.JSON(), nullable=False),
        sa.Column("auth_method", sa.String(32), nullable=False),
        sa.Column("application_type", sa.String(16)),
        sa.Column("secret_hash", sa.String(64)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "mcp_oauth_requests",
        *common(),
        sa.Column("request_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("mcp_oauth_clients.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("redirect_uri", sa.String(2000), nullable=False),
        sa.Column("state", sa.String(1024), nullable=False),
        sa.Column("code_challenge", sa.String(43), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("resource", sa.String(2000), nullable=False),
        sa.Column("issuer", sa.String(2000), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("denied_at", sa.DateTime(timezone=True)),
        sa.Column("code_hash", sa.String(64), unique=True),
        sa.Column("code_expires_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "mcp_oauth_grants",
        *common(),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("mcp_oauth_clients.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("refresh_hash", sa.String(64), unique=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("redirect_uri", sa.String(2000), nullable=False),
        sa.Column("resource", sa.String(2000), nullable=False),
        sa.Column("issuer", sa.String(2000), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True)),
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_mcp_oauth_grants_user_id", "mcp_oauth_grants", ["user_id"])
    op.create_index("ix_mcp_oauth_grants_family_id", "mcp_oauth_grants", ["family_id"])


def downgrade():
    connection = op.get_bind()
    for table in ("mcp_oauth_grants", "mcp_oauth_requests", "mcp_oauth_clients"):
        if connection.scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError(
                "Remote MCP OAuth tables contain data; export and review before downgrade"
            )
    op.drop_table("mcp_oauth_grants")
    op.drop_table("mcp_oauth_requests")
    op.drop_table("mcp_oauth_clients")
