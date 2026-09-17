"""Add user-facing business scenario navigation without changing intake."""

from alembic import op
import sqlalchemy as sa


revision = "b8c4d2e6f901"
down_revision = "e6f7a8b9c012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_scenarios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "asset_scenario_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source_type", sa.String(length=32), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), server_default=sa.text("0.5"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["business_scenarios.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "scenario_id"),
    )
    op.create_index(
        "ix_asset_scenario_links_scenario",
        "asset_scenario_links",
        ["scenario_id", "asset_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_asset_scenario_links_scenario", table_name="asset_scenario_links")
    op.drop_table("asset_scenario_links")
    op.drop_table("business_scenarios")
