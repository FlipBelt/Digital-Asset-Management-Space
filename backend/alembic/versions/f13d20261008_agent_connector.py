"""Add opt-in delegated agent grants, idempotency and private incubations."""

import sqlalchemy as sa
from alembic import op

revision = "f13d20261008"
down_revision = "f13c20260928"
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
        "agent_grants",
        *common(),
        sa.Column("device_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("client_name", sa.String(80), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("device_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_polled_at", sa.DateTime(timezone=True)),
        sa.Column("token_hash", sa.String(64), unique=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "agent_operations",
        *common(),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
    )
    op.create_index("ix_agent_operations_user_id", "agent_operations", ["user_id"])
    op.create_table(
        "agent_incubations",
        *common(),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("workflow_summary", sa.Text(), nullable=False),
        sa.Column("opportunity_summary", sa.Text(), nullable=False),
        sa.Column("blueprint_summary", sa.Text(), nullable=False),
        sa.Column("next_step", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id")),
    )
    op.create_index("ix_agent_incubations_user_id", "agent_incubations", ["user_id"])


def downgrade():
    # Application rollback keeps these additive tables. Never discard live connector data.
    connection = op.get_bind()
    for table in ("agent_incubations", "agent_operations", "agent_grants"):
        count = connection.scalar(sa.text(f"SELECT count(*) FROM {table}"))
        if count:
            raise RuntimeError(
                "Connector tables contain data; export and review before schema downgrade"
            )

    op.drop_table("agent_incubations")
    op.drop_table("agent_operations")
    op.drop_table("agent_grants")
