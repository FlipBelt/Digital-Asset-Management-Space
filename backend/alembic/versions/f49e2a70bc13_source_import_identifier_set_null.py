"""Keep historical identifiers when an import record is removed.

Revision ID: f49e2a70bc13
Revises: e38f5b61d2c4
Create Date: 2026-08-10
"""

from alembic import op


revision = "f49e2a70bc13"
down_revision = "e38f5b61d2c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_asset_identifiers_source_import_record_id_source_imp_ee26",
        "asset_identifiers",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_asset_identifiers_source_import_record_id_source_imp_ee26",
        "asset_identifiers",
        "source_import_records",
        ["source_import_record_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_asset_identifiers_source_import_record_id_source_imp_ee26",
        "asset_identifiers",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_asset_identifiers_source_import_record_id_source_imp_ee26",
        "asset_identifiers",
        "source_import_records",
        ["source_import_record_id"],
        ["id"],
    )
