"""Cascade sequence rows for removed legal entities and asset types.

Revision ID: e38f5b61d2c4
Revises: d10b4c3a9e82
Create Date: 2026-08-10
"""

from alembic import op


revision = "e38f5b61d2c4"
down_revision = "d10b4c3a9e82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, target in [
        ("fk_asset_code_sequences_legal_entity_id_legal_entities", "legal_entities"),
        ("fk_asset_code_sequences_asset_type_id_asset_types", "asset_types"),
    ]:
        op.drop_constraint(name, "asset_code_sequences", type_="foreignkey")
        op.create_foreign_key(
            name,
            "asset_code_sequences",
            target,
            ["legal_entity_id" if target == "legal_entities" else "asset_type_id"],
            ["id"],
            ondelete="CASCADE",
        )
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
    for name, target in [
        ("fk_asset_code_sequences_legal_entity_id_legal_entities", "legal_entities"),
        ("fk_asset_code_sequences_asset_type_id_asset_types", "asset_types"),
    ]:
        op.drop_constraint(name, "asset_code_sequences", type_="foreignkey")
        op.create_foreign_key(
            name,
            "asset_code_sequences",
            target,
            ["legal_entity_id" if target == "legal_entities" else "asset_type_id"],
            ["id"],
        )
