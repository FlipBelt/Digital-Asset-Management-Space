"""Seed editable baseline field templates for governed asset types.

Revision ID: a33c5d9e8214
Revises: f49e2a70bc13
Create Date: 2026-08-10
"""

from uuid import uuid4

import sqlalchemy as sa

from alembic import op


revision = "a33c5d9e8214"
down_revision = "f49e2a70bc13"
branch_labels = None
depends_on = None


TEMPLATES = [
    ("cloud_server", "instance_id", "实例 ID", "text", False, "实例与网络", "云平台原生实例标识，可暂不填写", 1),
    ("cloud_server", "region", "地域", "text", False, "实例与网络", "例如 cn-hangzhou", 2),
    ("cloud_server", "availability_zone", "可用区", "text", False, "实例与网络", None, 3),
    ("cloud_server", "specification", "规格配置", "text", False, "计算与系统", "例如 4 vCPU / 16 GiB", 4),
    ("cloud_server", "operating_system", "操作系统", "text", False, "计算与系统", None, 5),
    ("cloud_server", "private_ip", "私网 IP", "text", False, "实例与网络", None, 6),
    ("cloud_server", "public_ip", "公网 IP", "text", False, "实例与网络", "敏感信息，按权限展示", 7),
    ("cloud_server", "vpc_id", "VPC ID", "text", False, "实例与网络", None, 8),
    ("cloud_database", "instance_id", "实例 ID", "text", False, "实例与连接", "云平台原生实例标识，可暂不填写", 1),
    ("cloud_database", "engine", "数据库引擎", "text", False, "实例与连接", "例如 MySQL、PostgreSQL", 2),
    ("cloud_database", "version", "引擎版本", "text", False, "实例与连接", None, 3),
    ("cloud_database", "endpoint", "连接地址", "text", False, "实例与连接", "不填写密码或连接串 Secret", 4),
    ("saas_subscription", "plan", "订阅套餐", "text", False, "订阅信息", None, 1),
    ("saas_subscription", "seat_count", "席位数量", "number", False, "订阅信息", None, 2),
    ("saas_subscription", "renewal_cycle", "续费周期", "text", False, "订阅信息", "例如月付、年付", 3),
    ("api_service", "api_endpoint", "API 地址", "text", False, "接入信息", None, 1),
    ("api_service", "api_version", "API 版本", "text", False, "接入信息", None, 2),
    ("api_service", "quota", "配额说明", "textarea", False, "接入信息", None, 3),
    ("platform_tenant", "tenant_id", "平台租户 / 企业 ID", "text", False, "账号主体", "平台原生标识，可暂不填写", 1),
    ("platform_tenant", "account_scope_note", "账号范围说明", "textarea", False, "账号主体", None, 2),
]


def upgrade() -> None:
    connection = op.get_bind()
    for type_code, field_key, label, data_type, is_required, group_name, help_text, sort_order in TEMPLATES:
        asset_type_id = connection.scalar(
            sa.text("SELECT id FROM asset_types WHERE code = :code AND archived_at IS NULL"),
            {"code": type_code},
        )
        if asset_type_id is None:
            continue
        exists = connection.scalar(
            sa.text(
                "SELECT 1 FROM asset_field_definitions "
                "WHERE asset_type_id = :asset_type_id AND field_key = :field_key "
                "AND archived_at IS NULL"
            ),
            {"asset_type_id": asset_type_id, "field_key": field_key},
        )
        if exists:
            continue
        connection.execute(
            sa.text(
                "INSERT INTO asset_field_definitions "
                "(id, asset_type_id, field_key, label, data_type, is_required, options, "
                "group_name, help_text, unit, validation, confidentiality, is_searchable, "
                "completeness_weight, sort_order, created_at, updated_at) "
                "VALUES (:id, :asset_type_id, :field_key, :label, :data_type, :is_required, "
                "NULL, :group_name, :help_text, NULL, '{}'::jsonb, :confidentiality, "
                "TRUE, 0, :sort_order, now(), now())"
            ),
            {
                "id": uuid4(), "asset_type_id": asset_type_id, "field_key": field_key,
                "label": label, "data_type": data_type, "is_required": is_required,
                "group_name": group_name, "help_text": help_text, "confidentiality": "sensitive" if field_key in {"public_ip", "endpoint"} else "internal", "sort_order": sort_order,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    for type_code, field_key, *_ in TEMPLATES:
        connection.execute(
            sa.text(
                "DELETE FROM asset_field_definitions WHERE field_key = :field_key "
                "AND asset_type_id IN (SELECT id FROM asset_types WHERE code = :type_code)"
            ),
            {"field_key": field_key, "type_code": type_code},
        )
