"""add optional direct links between instantiated assets and platforms

Revision ID: f7e2b8c4d901
Revises: a6f4c2d8b719
Create Date: 2026-08-28

L3 platforms are catalog objects, not assets.  Keep direct L2/L3 and L6/L3
associations outside the L4 tenant table so an optional relation never forces a
placeholder company platform account.
"""

import sqlalchemy as sa
from alembic import op


revision = "f7e2b8c4d901"
down_revision = "a6f4c2d8b719"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_platform_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("platform_id", sa.Uuid(), nullable=False),
        sa.Column("relation_type", sa.String(length=50), server_default="uses", nullable=False),
        sa.Column("source_type", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("source_import_record_id", sa.Uuid(), nullable=True),
        sa.Column("review_status", sa.String(length=32), server_default="pending_review", nullable=False),
        sa.Column("confirmed_by_person_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_import_record_id"], ["source_import_records.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["confirmed_by_person_id"], ["people.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_asset_platform_links_active",
        "asset_platform_links",
        ["asset_id", "platform_id", "relation_type"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_asset_platform_links_active", table_name="asset_platform_links")
    op.drop_table("asset_platform_links")
