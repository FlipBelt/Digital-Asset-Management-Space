"""add progressive entity profiles and field entry rules

Revision ID: a1b7c9d2e403
Revises: f6e2a9b1c403
Create Date: 2026-08-24

This migration is intentionally additive.  It does not update, reclassify, or
create records for any existing legal entity or asset.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "a1b7c9d2e403"
down_revision = "f6e2a9b1c403"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_entity_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("legal_entity_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("jurisdiction", sa.String(length=120), nullable=True),
        sa.Column("registration_status", sa.String(length=32), nullable=True),
        sa.Column("legal_representative", sa.String(length=120), nullable=True),
        sa.Column("established_on", sa.Date(), nullable=True),
        sa.Column("registered_address", sa.Text(), nullable=True),
        sa.Column("registered_capital", sa.String(length=120), nullable=True),
        sa.Column("business_scope", sa.Text(), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("verification_status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["legal_entity_id"], ["legal_entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legal_entity_id"),
    )
    op.create_table(
        "legal_entity_identifiers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("legal_entity_id", sa.Uuid(), nullable=False),
        sa.Column("namespace", sa.String(length=80), server_default="cn", nullable=False),
        sa.Column("identifier_type", sa.String(length=80), nullable=False),
        sa.Column("identifier_value", sa.String(length=200), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("verification_status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["legal_entity_id"], ["legal_entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("namespace", "identifier_type", "identifier_value"),
    )
    op.create_index(
        "ix_legal_entity_identifiers_entity",
        "legal_entity_identifiers",
        ["legal_entity_id", "identifier_type"],
    )
    op.add_column(
        "asset_field_definitions",
        sa.Column("entry_visibility", sa.String(length=32), server_default="optional", nullable=False),
    )
    op.add_column(
        "asset_field_definitions",
        sa.Column("requirement_stage", sa.String(length=32), server_default="optional", nullable=False),
    )
    op.add_column(
        "asset_field_definitions",
        sa.Column("applies_to_existing", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "asset_field_definitions",
        sa.Column(
            "condition_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("platform_tenants", sa.Column("evidence_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("platform_tenants", "evidence_note")
    op.drop_column("asset_field_definitions", "condition_rules")
    op.drop_column("asset_field_definitions", "applies_to_existing")
    op.drop_column("asset_field_definitions", "requirement_stage")
    op.drop_column("asset_field_definitions", "entry_visibility")
    op.drop_index("ix_legal_entity_identifiers_entity", table_name="legal_entity_identifiers")
    op.drop_table("legal_entity_identifiers")
    op.drop_table("legal_entity_profiles")
