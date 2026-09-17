"""Add the first concise core-field templates for the six supported L6 types."""

import json
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "d4e6f7a8b901"
down_revision = "c8d4e5f6a701"
branch_labels = None
depends_on = None


CORE_TYPES = {
    "api_service": {
        "api_endpoint": ("API 地址", "text", "接入信息", None, "core", "internal"),
        "auth_method": (
            "认证方式",
            "text",
            "接入信息",
            ["API Key", "Bearer Token", "OAuth", "无认证", "其他"],
            "core",
            "internal",
        ),
        "api_key": ("API Key / Token", "text", "接入信息", None, "core", "sensitive"),
        "api_version": ("API 版本", "text", "接入信息", None, "optional", "internal"),
        "quota": ("配额说明", "textarea", "接入信息", None, "optional", "internal"),
        "use_purpose": ("使用用途", "textarea", "使用情况", None, "optional", "internal"),
    },
    "saas_subscription": {
        "plan": ("订阅套餐 / 版本", "text", "订阅信息", None, "core", "internal"),
        "usage_purpose": ("套餐用途", "text", "订阅信息", None, "core", "internal"),
        "seat_count": ("席位数量", "number", "订阅信息", None, "optional", "internal"),
        "renewal_cycle": ("续费周期", "text", "订阅信息", None, "optional", "internal"),
        "renewal_day": ("续费日", "number", "订阅信息", None, "optional", "internal"),
        "monthly_budget": ("月预算", "number", "费用信息", None, "optional", "internal"),
        "currency": ("预算币种", "text", "费用信息", ["CNY", "USD"], "optional", "internal"),
        "payment_method": ("付款方式", "text", "费用信息", None, "optional", "internal"),
        "settlement_method": ("结算方式", "text", "费用信息", None, "optional", "internal"),
    },
    "cloud_server": {
        "instance_id": ("实例 ID", "text", "实例与网络", None, "core", "internal"),
        "region": ("地域", "text", "实例与网络", None, "core", "internal"),
        "availability_zone": ("可用区", "text", "实例与网络", None, "optional", "internal"),
        "specification": ("规格配置", "text", "计算与系统", None, "optional", "internal"),
        "operating_system": ("操作系统", "text", "计算与系统", None, "optional", "internal"),
        "private_ip": ("私网 IP", "text", "实例与网络", None, "optional", "sensitive"),
        "public_ip": ("公网 IP", "text", "实例与网络", None, "optional", "sensitive"),
        "vpc_id": ("VPC ID", "text", "实例与网络", None, "optional", "internal"),
    },
    "email_service": {
        "service_domain": ("邮箱域名 / 地址", "text", "邮箱信息", None, "core", "internal"),
        "management_url": ("管理入口", "text", "邮箱信息", None, "optional", "internal"),
        "mailbox_count": ("邮箱数量", "number", "邮箱信息", None, "optional", "internal"),
        "plan": ("服务套餐", "text", "订阅信息", None, "optional", "internal"),
        "admin_identity": ("管理员身份说明", "text", "管理信息", None, "optional", "sensitive"),
        "renewal_date": ("到期 / 续费日期", "date", "订阅信息", None, "optional", "internal"),
    },
    "vpn_network": {
        "vpn_endpoint": ("VPN 入口", "text", "接入信息", None, "core", "internal"),
        "usage_purpose": ("使用用途", "text", "接入信息", None, "core", "internal"),
        "protocol": ("协议类型", "text", "网络信息", None, "optional", "internal"),
        "network_scope": ("网络范围", "textarea", "网络信息", None, "optional", "internal"),
        "renewal_date": ("到期 / 续费日期", "date", "订阅信息", None, "optional", "internal"),
        "provider_note": ("服务商说明", "text", "服务信息", None, "optional", "internal"),
    },
}


def upgrade() -> None:
    connection = op.get_bind()
    for type_code, fields in CORE_TYPES.items():
        asset_type_id = connection.scalar(
            sa.text("SELECT id FROM asset_types WHERE code = :code AND archived_at IS NULL"),
            {"code": type_code},
        )
        if asset_type_id is None:
            continue
        for sort_order, (field_key, definition) in enumerate(fields.items(), start=1):
            label, data_type, group_name, options, visibility, confidentiality = definition
            existing = connection.scalar(
                sa.text(
                    "SELECT id FROM asset_field_definitions "
                    "WHERE asset_type_id = :asset_type_id AND field_key = :field_key"
                ),
                {"asset_type_id": asset_type_id, "field_key": field_key},
            )
            if existing is None:
                connection.execute(
                    sa.text(
                        "INSERT INTO asset_field_definitions "
                        "(id, asset_type_id, field_key, label, data_type, is_required, options, "
                        "group_name, help_text, unit, validation, confidentiality, is_searchable, "
                        "completeness_weight, sort_order, entry_visibility, requirement_stage, "
                        "applies_to_existing, condition_rules, created_at, updated_at) "
                        "VALUES (:id, :asset_type_id, :field_key, :label, :data_type, false, "
                        "CAST(:options AS jsonb), :group_name, NULL, NULL, '{}'::jsonb, "
                        ":confidentiality, false, 0, :sort_order, :entry_visibility, "
                        "'optional', true, '{}'::jsonb, now(), now())"
                    ),
                    {
                        "id": uuid4(),
                        "asset_type_id": asset_type_id,
                        "field_key": field_key,
                        "label": label,
                        "data_type": data_type,
                        "options": json.dumps(options) if options is not None else None,
                        "group_name": group_name,
                        "confidentiality": confidentiality,
                        "sort_order": sort_order,
                        "entry_visibility": visibility,
                    },
                )
            else:
                connection.execute(
                    sa.text(
                        "UPDATE asset_field_definitions SET label = :label, "
                        "data_type = :data_type, "
                        "options = CAST(:options AS jsonb), group_name = :group_name, "
                        "confidentiality = :confidentiality, "
                        "entry_visibility = :entry_visibility, updated_at = now() WHERE id = :id"
                    ),
                    {
                        "id": existing,
                        "label": label,
                        "data_type": data_type,
                        "options": json.dumps(options) if options is not None else None,
                        "group_name": group_name,
                        "confidentiality": confidentiality,
                        "entry_visibility": visibility,
                    },
                )


def downgrade() -> None:
    connection = op.get_bind()
    for type_code, fields in CORE_TYPES.items():
        for field_key in fields:
            connection.execute(
                sa.text(
                    "DELETE FROM asset_field_definitions WHERE field_key = :field_key "
                    "AND asset_type_id IN (SELECT id FROM asset_types WHERE code = :type_code)"
                ),
                {"field_key": field_key, "type_code": type_code},
            )
