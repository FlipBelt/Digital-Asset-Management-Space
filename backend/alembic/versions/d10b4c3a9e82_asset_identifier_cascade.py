"""Cascade identifier cleanup when an asset is deleted in maintenance tooling.

Revision ID: d10b4c3a9e82
Revises: c95e2b4d8a71
Create Date: 2026-08-10
"""

from alembic import op


revision = "d10b4c3a9e82"
down_revision = "c95e2b4d8a71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_asset_identifiers_asset_id_assets", "asset_identifiers", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_asset_identifiers_asset_id_assets",
        "asset_identifiers",
        "assets",
        ["asset_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_asset_identifiers_asset_id_assets", "asset_identifiers", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_asset_identifiers_asset_id_assets",
        "asset_identifiers",
        "assets",
        ["asset_id"],
        ["id"],
    )
