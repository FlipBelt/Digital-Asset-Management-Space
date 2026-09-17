"""add governed asset metadata

Revision ID: b24d7f1a6e93
Revises: f41d5e9a2c70
Create Date: 2026-08-10 15:35:00.000000
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b24d7f1a6e93"
down_revision: str | Sequence[str] | None = "f41d5e9a2c70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps(*, archived: bool = False) -> list[sa.Column]:
    columns = [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]
    if archived:
        columns.append(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    return columns


def upgrade() -> None:
    op.add_column(
        "assets", sa.Column("ownership_scope", sa.String(length=32), server_default="pending", nullable=False)
    )
    op.execute(
        "UPDATE assets SET ownership_scope = CASE "
        "WHEN owner_department_id IS NOT NULL THEN 'department' "
        "WHEN status = 'active' AND review_status = 'approved' THEN 'company' "
        "ELSE 'pending' END"
    )

    op.add_column(
        "asset_types", sa.Column("code_prefix", sa.String(length=20), server_default="AST", nullable=False)
    )
    op.add_column(
        "asset_types", sa.Column("ownership_default", sa.String(length=32), server_default="manual", nullable=False)
    )
    op.execute(
        "UPDATE asset_types SET code_prefix = CASE code "
        "WHEN 'registration_identity' THEN 'REG' "
        "WHEN 'platform_tenant' THEN 'ACC' WHEN 'platform_account' THEN 'ACC' "
        "WHEN 'saas_subscription' THEN 'SUB' WHEN 'api_service' THEN 'API' "
        "WHEN 'cloud_server' THEN 'ECS' WHEN 'cloud_database' THEN 'DB' "
        "WHEN 'nas_storage' THEN 'STO' WHEN 'vpn_network' THEN 'NET' "
        "WHEN 'internal_system' THEN 'SYS' WHEN 'automation_script' THEN 'SYS' "
        "WHEN 'ai_workflow' THEN 'SYS' WHEN 'domain' THEN 'DOM' "
        "WHEN 'ssl_certificate' THEN 'CERT' WHEN 'hardware_device' THEN 'DEV' "
        "ELSE 'AST' END"
    )
    op.execute(
        "UPDATE asset_types SET ownership_default = CASE "
        "WHEN code IN ('platform_tenant', 'platform_account') THEN 'company' "
        "WHEN code IN ('cloud_server', 'cloud_database', 'nas_storage', 'vpn_network') THEN 'responsible_department' "
        "ELSE 'manual' END"
    )

    for name, column in [
        ("group_name", sa.Column("group_name", sa.String(length=120), server_default="基础信息", nullable=False)),
        ("help_text", sa.Column("help_text", sa.Text(), nullable=True)),
        ("unit", sa.Column("unit", sa.String(length=40), nullable=True)),
        ("validation", sa.Column("validation", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False)),
        ("confidentiality", sa.Column("confidentiality", sa.String(length=32), server_default="internal", nullable=False)),
        ("is_searchable", sa.Column("is_searchable", sa.Boolean(), server_default=sa.false(), nullable=False)),
        ("completeness_weight", sa.Column("completeness_weight", sa.Integer(), server_default="0", nullable=False)),
    ]:
        op.add_column("asset_field_definitions", column)

    op.create_table(
        "asset_code_sequences",
        sa.Column("legal_entity_id", sa.Uuid(), nullable=False),
        sa.Column("asset_type_id", sa.Uuid(), nullable=False),
        sa.Column("last_value", sa.Integer(), server_default="0", nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["legal_entity_id"], ["legal_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_type_id"], ["asset_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legal_entity_id", "asset_type_id"),
    )
    op.create_table(
        "asset_identifiers",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("namespace", sa.String(length=80), nullable=False),
        sa.Column("identifier_type", sa.String(length=80), nullable=False),
        sa.Column("identifier_value", sa.String(length=500), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("verification_status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("source_import_record_id", sa.Uuid(), nullable=True),
        sa.Column("confidentiality", sa.String(length=32), server_default="internal", nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(archived=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_import_record_id"], ["source_import_records.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_asset_identifiers_active_value",
        "asset_identifiers",
        ["namespace", "identifier_type", "identifier_value"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "ix_asset_identifiers_lookup",
        "asset_identifiers",
        ["namespace", "identifier_type", "identifier_value"],
    )
    relation_table = op.create_table(
        "relation_definitions",
        sa.Column("relation_type", sa.String(length=50), nullable=False),
        sa.Column("source_type_code", sa.String(length=80), nullable=False),
        sa.Column("target_type_code", sa.String(length=80), nullable=False),
        sa.Column("forward_label", sa.String(length=100), nullable=False),
        sa.Column("inverse_label", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=32), server_default="upstream", nullable=False),
        sa.Column("source_max_count", sa.Integer(), nullable=True),
        sa.Column("target_max_count", sa.Integer(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.false(), nullable=False),
        *timestamps(archived=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("relation_type", "source_type_code", "target_type_code"),
    )
    relation_rows = [
        ("REGISTERED_BY", "platform_tenant", "registration_identity", "注册身份为", "注册了账号", "upstream", 1),
        ("REGISTERED_BY", "platform_account", "registration_identity", "注册身份为", "注册了账号", "upstream", 1),
        ("PURCHASED_VIA", "saas_subscription", "platform_tenant", "购买自", "开通了服务", "upstream", 1),
        ("PURCHASED_VIA", "api_service", "platform_tenant", "购买自", "开通了服务", "upstream", 1),
        ("PURCHASED_VIA", "cloud_server", "platform_tenant", "购买自", "购买了资源", "upstream", 1),
        ("PURCHASED_VIA", "cloud_database", "platform_tenant", "购买自", "购买了资源", "upstream", 1),
        ("PURCHASED_VIA", "nas_storage", "platform_tenant", "购买自", "购买了资源", "upstream", 1),
        ("PURCHASED_VIA", "vpn_network", "platform_tenant", "购买自", "购买了资源", "upstream", 1),
        ("DEPLOYED_ON", "internal_system", "cloud_server", "部署在", "承载系统", "upstream", None),
        ("DEPLOYED_ON", "automation_script", "cloud_server", "部署在", "承载自动化", "upstream", None),
        ("DEPLOYED_ON", "ai_workflow", "cloud_server", "部署在", "承载工作流", "upstream", None),
        ("CALLS", "internal_system", "api_service", "调用", "被调用", "upstream", None),
        ("CALLS", "ai_workflow", "api_service", "调用", "被调用", "upstream", None),
        ("USES", "internal_system", "saas_subscription", "使用", "被使用", "upstream", None),
        ("STORED_IN", "business_database", "nas_storage", "存储在", "存放了数据", "upstream", None),
        ("REPLACES", "*", "*", "替代", "被替代", "peer", None),
    ]
    op.bulk_insert(
        relation_table,
        [
            {
                "id": uuid4(), "relation_type": relation_type, "source_type_code": source,
                "target_type_code": target, "forward_label": forward, "inverse_label": inverse,
                "category": category, "source_max_count": max_count, "target_max_count": None,
                "is_system": True,
            }
            for relation_type, source, target, forward, inverse, category, max_count in relation_rows
        ],
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT roles.id, permissions.id
        FROM roles, permissions
        WHERE roles.code = 'employee' AND permissions.code = 'asset.write'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("relation_definitions")
    op.drop_index("ix_asset_identifiers_lookup", table_name="asset_identifiers")
    op.drop_index("uq_asset_identifiers_active_value", table_name="asset_identifiers")
    op.drop_table("asset_identifiers")
    op.drop_table("asset_code_sequences")
    for column in [
        "completeness_weight", "is_searchable", "confidentiality", "validation", "unit", "help_text", "group_name"
    ]:
        op.drop_column("asset_field_definitions", column)
    op.drop_column("asset_types", "ownership_default")
    op.drop_column("asset_types", "code_prefix")
    op.drop_column("assets", "ownership_scope")
