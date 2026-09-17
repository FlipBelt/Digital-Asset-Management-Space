"""add business object, import, and asset map models

Revision ID: f41d5e9a2c70
Revises: ea42c8b6f190
Create Date: 2026-08-07 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f41d5e9a2c70"
down_revision: str | Sequence[str] | None = "ea42c8b6f190"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps(*, archived: bool = False) -> list[sa.Column]:
    columns = [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    ]
    if archived:
        columns.append(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    return columns


def upgrade() -> None:
    op.add_column(
        "platforms",
        sa.Column("review_status", sa.String(length=32), server_default="approved", nullable=False),
    )
    op.add_column("platforms", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("platforms", sa.Column("submitted_by_person_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_platforms_submitted_by_person_id_people"),
        "platforms",
        "people",
        ["submitted_by_person_id"],
        ["id"],
    )

    op.alter_column("platform_tenants", "tenant_identifier", existing_type=sa.String(200), nullable=True)
    op.add_column(
        "platform_tenants", sa.Column("external_identifier_type", sa.String(80), nullable=True)
    )
    op.add_column(
        "platform_tenants",
        sa.Column("ownership_nature", sa.String(32), server_default="company_owned", nullable=False),
    )
    op.add_column(
        "platform_tenants",
        sa.Column("account_scope", sa.String(32), server_default="primary_account", nullable=False),
    )
    op.add_column(
        "platform_tenants",
        sa.Column("verification_status", sa.String(32), server_default="pending", nullable=False),
    )

    op.add_column("accounts", sa.Column("parent_account_id", sa.Uuid(), nullable=True))
    op.add_column(
        "accounts",
        sa.Column("account_kind", sa.String(32), server_default="member_login", nullable=False),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "login_method", sa.String(32), server_default="registration_identity", nullable=False
        ),
    )
    op.add_column(
        "accounts", sa.Column("account_role", sa.String(32), server_default="member", nullable=False)
    )
    op.add_column("accounts", sa.Column("primary_person_id", sa.Uuid(), nullable=True))
    op.add_column("accounts", sa.Column("legacy_source_id", sa.String(200), nullable=True))
    op.add_column(
        "accounts",
        sa.Column(
            "legacy_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        op.f("fk_accounts_parent_account_id_accounts"),
        "accounts",
        "accounts",
        ["parent_account_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_accounts_primary_person_id_people"),
        "accounts",
        "people",
        ["primary_person_id"],
        ["id"],
    )

    op.create_table(
        "registration_identity_profiles",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("identity_type", sa.String(32), nullable=False),
        sa.Column("identifier_value", sa.String(500), nullable=False),
        sa.Column("identifier_masked", sa.String(500), nullable=False),
        sa.Column("identifier_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_nature", sa.String(32), server_default="company_owned", nullable=False),
        sa.Column("custodian_person_id", sa.Uuid(), nullable=True),
        sa.Column("verification_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(archived=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["custodian_person_id"], ["people.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id"),
        sa.UniqueConstraint("identifier_fingerprint"),
    )

    op.create_table(
        "platform_account_registration_identities",
        sa.Column("platform_tenant_id", sa.Uuid(), nullable=False),
        sa.Column("registration_identity_asset_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(32), server_default="primary", nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("starts_at", sa.Date(), nullable=True),
        sa.Column("ends_at", sa.Date(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["platform_tenant_id"], ["platform_tenants.id"]),
        sa.ForeignKeyConstraint(["registration_identity_asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform_tenant_id", "registration_identity_asset_id", "role", name="uq_tenant_identity_role"
        ),
    )

    op.create_table(
        "access_grants",
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("person_id", sa.Uuid(), nullable=True),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("grant_type", sa.String(50), nullable=False),
        sa.Column("grant_role", sa.String(50), server_default="member", nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("starts_at", sa.Date(), nullable=True),
        sa.Column("ends_at", sa.Date(), nullable=True),
        sa.Column("monthly_budget", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("renewal_day", sa.Integer(), nullable=True),
        sa.Column("payment_reference", sa.String(300), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("legacy_source_id", sa.String(200), nullable=True),
        sa.Column(
            "legacy_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        *timestamps(archived=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"]),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "resource_profiles",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("resource_family", sa.String(50), nullable=False),
        sa.Column("managed_under_account_id", sa.Uuid(), nullable=True),
        sa.Column("parent_resource_asset_id", sa.Uuid(), nullable=True),
        sa.Column("external_identifier_type", sa.String(80), nullable=True),
        sa.Column("external_identifier_value", sa.String(500), nullable=True),
        sa.Column("management_url", sa.String(1000), nullable=True),
        sa.Column("verification_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(archived=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["managed_under_account_id"], ["platform_tenants.id"]),
        sa.ForeignKeyConstraint(["parent_resource_asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id"),
    )

    op.create_table(
        "credential_records",
        sa.Column("subject_type", sa.String(50), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("credential_kind", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("masked_hint", sa.String(300), nullable=True),
        sa.Column("storage_mode", sa.String(32), server_default="external_vault", nullable=False),
        sa.Column("content_reference", sa.String(1000), nullable=True),
        sa.Column("custodian_person_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *timestamps(archived=True),
        sa.ForeignKeyConstraint(["custodian_person_id"], ["people.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "source_import_records",
        sa.Column("import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.String(50), nullable=False),
        sa.Column("source_identifier", sa.String(500), nullable=True),
        sa.Column(
            "raw_payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("suggested_object_type", sa.String(80), nullable=True),
        sa.Column("suggested_name", sa.String(300), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("mapping_status", sa.String(32), server_default="pending_review", nullable=False),
        sa.Column("canonical_asset_id", sa.Uuid(), nullable=True),
        sa.Column("canonical_account_id", sa.Uuid(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        *timestamps(archived=True),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"]),
        sa.ForeignKeyConstraint(["canonical_asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["canonical_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("source_import_records")
    op.drop_table("credential_records")
    op.drop_table("resource_profiles")
    op.drop_table("access_grants")
    op.drop_table("platform_account_registration_identities")
    op.drop_table("registration_identity_profiles")
    op.drop_constraint(op.f("fk_accounts_primary_person_id_people"), "accounts", type_="foreignkey")
    op.drop_constraint(op.f("fk_accounts_parent_account_id_accounts"), "accounts", type_="foreignkey")
    for column in [
        "legacy_metadata",
        "legacy_source_id",
        "primary_person_id",
        "account_role",
        "login_method",
        "account_kind",
        "parent_account_id",
    ]:
        op.drop_column("accounts", column)
    for column in [
        "verification_status",
        "account_scope",
        "ownership_nature",
        "external_identifier_type",
    ]:
        op.drop_column("platform_tenants", column)
    op.alter_column("platform_tenants", "tenant_identifier", existing_type=sa.String(200), nullable=False)
    op.drop_constraint(op.f("fk_platforms_submitted_by_person_id_people"), "platforms", type_="foreignkey")
    op.drop_column("platforms", "submitted_by_person_id")
    op.drop_column("platforms", "description")
    op.drop_column("platforms", "review_status")
