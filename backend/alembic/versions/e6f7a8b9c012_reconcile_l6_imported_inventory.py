"""Reconcile imported L6 inventory against confirmed source evidence.

This is a data repair, not a schema change.  It preserves the source import
rows and archives only the Aliyun-derived summaries and the three synthetic
API objects that were created from internal-system APIID values.
"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "e6f7a8b9c012"
down_revision = "d4e6f7a8b901"
branch_labels = None
depends_on = None


ALIYUN_ASSET_CODES = [
    "服务器-U-003",
    "服务器-U-005",
    "服务器-U-009",
    "服务器-U-010",
    "服务器-U-014",
    "服务器-U-023",
    "服务器-U-025",
    "服务器-U-026",
    "服务器-U-039",
    "服务器-U-042",
    "服务器-U-060",
    "服务器-U-075",
    "服务器-U-076",
    "服务器-U-077",
]

SYNTHETIC_API_CODES = ["订阅-U-001", "订阅-U-013", "订阅-U-015"]


def _ids_for_codes(connection: sa.Connection, codes: list[str]) -> list[str]:
    statement = sa.text(
        "SELECT id FROM assets "
        "WHERE asset_code IN :codes AND archived_at IS NULL"
    ).bindparams(sa.bindparam("codes", expanding=True))
    return [str(row[0]) for row in connection.execute(statement, {"codes": codes})]


def _archive_assets(connection: sa.Connection, asset_ids: list[str]) -> None:
    if not asset_ids:
        return
    bind_ids = sa.bindparam("asset_ids", expanding=True)
    now = sa.text("now()")
    for table in (
        "asset_platform_links",
        "asset_responsibilities",
        "asset_identifiers",
        "service_instances",
        "resource_profiles",
    ):
        connection.execute(
            sa.text(
                f"UPDATE {table} SET archived_at = COALESCE(archived_at, {now.text}) "
                f"WHERE asset_id IN :asset_ids AND archived_at IS NULL"
            ).bindparams(bind_ids),
            {"asset_ids": asset_ids},
        )
    connection.execute(
        sa.text(
            "UPDATE asset_relations SET archived_at = COALESCE(archived_at, now()) "
            "WHERE (source_asset_id IN :asset_ids OR target_asset_id IN :asset_ids) "
            "AND archived_at IS NULL"
        ).bindparams(bind_ids),
        {"asset_ids": asset_ids},
    )
    connection.execute(
        sa.text(
            "UPDATE assets SET archived_at = COALESCE(archived_at, now()), status = 'archived' "
            "WHERE id IN :asset_ids AND archived_at IS NULL"
        ).bindparams(bind_ids),
        {"asset_ids": asset_ids},
    )


def _restore_assets(connection: sa.Connection, codes: list[str]) -> None:
    statement = sa.text(
        "UPDATE assets SET archived_at = NULL, status = 'active' "
        "WHERE asset_code IN :codes"
    ).bindparams(sa.bindparam("codes", expanding=True))
    connection.execute(statement, {"codes": codes})


def upgrade() -> None:
    connection = op.get_bind()

    aliyun_ids = _ids_for_codes(connection, ALIYUN_ASSET_CODES)
    _archive_assets(connection, aliyun_ids)
    if aliyun_ids:
        connection.execute(
            sa.text(
                "UPDATE source_import_records SET "
                "mapping_status = 'pending_review', canonical_asset_id = NULL, "
                "review_note = '阿里云目录仅保留来源证据；没有明确实例事实，不自动建立 L6。' "
                "WHERE canonical_asset_id IN :asset_ids"
            ).bindparams(sa.bindparam("asset_ids", expanding=True)),
            {"asset_ids": aliyun_ids},
        )

    synthetic_ids = _ids_for_codes(connection, SYNTHETIC_API_CODES)
    _archive_assets(connection, synthetic_ids)

    # Correct DD-001: its source type is DingTalk Wukong, while “API 接入” is
    # only a usage capability and must not change the subscription type.
    connection.execute(
        sa.text(
            "UPDATE assets SET asset_type_id = "
            "(SELECT id FROM asset_types WHERE code = 'saas_subscription') "
            "WHERE asset_code = '订阅-U-007' AND archived_at IS NULL"
        )
    )

    # Rebuild the three evidenced internal-system -> API relations against the
    # actual API assets, not the synthetic API objects archived above.
    relation_rows = (
        ("系统-U-001", "订阅-U-014", "API-001"),
        ("系统-U-003", "订阅-U-008", "API-002"),
        ("系统-U-002", "订阅-U-009", "API-003"),
    )
    insert = sa.text(
        "INSERT INTO asset_relations "
        "(id, created_at, updated_at, archived_at, source_asset_id, target_asset_id, "
        "relation_type, source_type, note) "
        "SELECT :id, now(), now(), NULL, source.id, target.id, 'calls', "
        "'import_reconciliation', :note "
        "FROM assets source, assets target "
        "WHERE source.asset_code = :source_code AND source.archived_at IS NULL "
        "AND target.asset_code = :target_code AND target.archived_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM asset_relations existing "
        "WHERE existing.source_asset_id = source.id AND existing.target_asset_id = target.id "
        "AND existing.relation_type = 'calls' AND existing.archived_at IS NULL)"
    )
    for source_code, target_code, legacy_id in relation_rows:
        connection.execute(
            insert,
            {
                "id": uuid4(),
                "source_code": source_code,
                "target_code": target_code,
                "note": f"老板台账 APIID={legacy_id}；内部系统调用已有 API 实例。",
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    _restore_assets(connection, ALIYUN_ASSET_CODES + SYNTHETIC_API_CODES)
    connection.execute(
        sa.text(
            "UPDATE assets SET asset_type_id = "
            "(SELECT id FROM asset_types WHERE code = 'api_service') "
            "WHERE asset_code = '订阅-U-007'"
        )
    )
    connection.execute(
        sa.text(
            "DELETE FROM asset_relations WHERE source_type = 'import_reconciliation'"
        )
    )
