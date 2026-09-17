"""Simplify internal asset codes for business users.

Revision ID: b92d3e71a4f6
Revises: a33c5d9e8214
Create Date: 2026-08-10
"""

from collections import defaultdict
from uuid import uuid4

import sqlalchemy as sa

from alembic import op


revision = "b92d3e71a4f6"
down_revision = "a33c5d9e8214"
branch_labels = None
depends_on = None


PREFIXES = {
    "registration_identity": "身份",
    "platform_tenant": "企业账号",
    "platform_account": "账号",
    "saas_subscription": "订阅",
    "api_service": "接口",
    "cloud_server": "服务器",
    "cloud_database": "数据库",
    "nas_storage": "存储",
    "vpn_network": "网络",
    "internal_system": "系统",
    "automation_script": "自动化",
    "ai_workflow": "工作流",
    "domain": "域名",
    "ssl_certificate": "证书",
    "hardware_device": "设备",
}


def upgrade() -> None:
    connection = op.get_bind()
    type_rows = connection.execute(
        sa.text("SELECT id, code FROM asset_types WHERE archived_at IS NULL")
    ).mappings().all()
    type_by_id = {row["id"]: row["code"] for row in type_rows}
    for row in type_rows:
        connection.execute(
            sa.text("UPDATE asset_types SET code_prefix = :prefix WHERE id = :id"),
            {"id": row["id"], "prefix": PREFIXES.get(row["code"], "资产")},
        )

    assets = connection.execute(
        sa.text(
            "SELECT id, legal_entity_id, asset_type_id, asset_code "
            "FROM assets ORDER BY legal_entity_id, asset_type_id, created_at, id"
        )
    ).mappings().all()
    counters: dict[tuple[object, object], int] = defaultdict(int)
    for asset in assets:
        key = (asset["legal_entity_id"], asset["asset_type_id"])
        counters[key] += 1
        prefix = PREFIXES.get(type_by_id.get(asset["asset_type_id"], ""), "资产")
        new_code = f"{prefix}-{counters[key]:03d}"
        old_code = asset["asset_code"]
        if old_code == new_code:
            continue
        namespace = f"legacy_internal_code:{asset['legal_entity_id']}"
        legacy_exists = connection.scalar(
            sa.text(
                "SELECT 1 FROM asset_identifiers WHERE namespace = :namespace "
                "AND identifier_type = 'asset_code' AND identifier_value = :value "
                "AND archived_at IS NULL"
            ),
            {"namespace": namespace, "value": old_code},
        )
        if not legacy_exists:
            connection.execute(
                sa.text(
                    "INSERT INTO asset_identifiers "
                    "(id, asset_id, namespace, identifier_type, identifier_value, is_primary, "
                    "verification_status, confidentiality, created_at, updated_at) "
                    "VALUES (:id, :asset_id, :namespace, 'asset_code', :value, FALSE, "
                    "'verified', 'internal', now(), now())"
                ),
                {"id": uuid4(), "asset_id": asset["id"], "namespace": namespace, "value": old_code},
            )
        connection.execute(
            sa.text("UPDATE assets SET asset_code = :code WHERE id = :id"),
            {"id": asset["id"], "code": new_code},
        )
        connection.execute(
            sa.text(
                "UPDATE asset_identifiers SET identifier_value = :code, updated_at = now() "
                "WHERE asset_id = :asset_id AND namespace = :namespace "
                "AND identifier_type = 'asset_code' AND archived_at IS NULL"
            ),
            {"asset_id": asset["id"], "namespace": f"internal:{asset['legal_entity_id']}", "code": new_code},
        )

    for (legal_entity_id, asset_type_id), last_value in counters.items():
        connection.execute(
            sa.text(
                "INSERT INTO asset_code_sequences "
                "(id, legal_entity_id, asset_type_id, last_value, created_at, updated_at) "
                "VALUES (:id, :legal_entity_id, :asset_type_id, :last_value, now(), now()) "
                "ON CONFLICT (legal_entity_id, asset_type_id) DO UPDATE "
                "SET last_value = EXCLUDED.last_value, updated_at = now()"
            ),
            {
                "id": uuid4(), "legal_entity_id": legal_entity_id,
                "asset_type_id": asset_type_id, "last_value": last_value,
            },
        )


def downgrade() -> None:
    # Original values are retained as historical identifiers. Reversing a
    # business-facing renumbering automatically would be misleading.
    pass
