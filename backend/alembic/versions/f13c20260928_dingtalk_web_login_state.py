"""Add expiring single-use state for DingTalk web login."""

import sqlalchemy as sa

from alembic import op

revision = "f13c20260928"
down_revision = "f13b20260928"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dingtalk_web_login_states",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("return_path", sa.String(2000), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_dingtalk_web_login_states_expires_at", "dingtalk_web_login_states", ["expires_at"]
    )


def downgrade() -> None:
    # Pending login challenges are disposable; no employee or business records are removed.
    op.drop_table("dingtalk_web_login_states")
