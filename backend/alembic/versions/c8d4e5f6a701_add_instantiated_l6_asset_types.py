"""add explicit L6 service subtypes used by the instance model

Revision ID: c8d4e5f6a701
Revises: f7e2b8c4d901
"""

from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "c8d4e5f6a701"
down_revision = "f7e2b8c4d901"
branch_labels = None
depends_on = None


NEW_TYPES = (
    ("email_service", "邮箱服务", "service_instance", "服务"),
    ("software_service", "软件与业务服务", "service_instance", "服务"),
    ("business_environment", "业务环境", "service_instance", "环境"),
)


def upgrade() -> None:
    bind = op.get_bind()
    category_id = bind.scalar(
        sa.text(
            "SELECT id FROM asset_categories "
            "WHERE code = 'saas_software' AND archived_at IS NULL"
        )
    )
    if category_id is None:
        category_id = uuid4()
        bind.execute(
            sa.text(
                "INSERT INTO asset_categories "
                "(id, code, name, sort_order, created_at, updated_at) "
                "VALUES (:id, 'saas_software', '外购软件与SaaS', 30, now(), now())"
            ),
            {"id": category_id},
        )
    for code, name, profile_kind, prefix in NEW_TYPES:
        exists = bind.scalar(
            sa.text("SELECT id FROM asset_types WHERE category_id = :category_id AND code = :code"),
            {"category_id": category_id, "code": code},
        )
        if exists is None:
            bind.execute(
                sa.text(
                    "INSERT INTO asset_types "
                    "(id, category_id, code, name, profile_kind, code_prefix, ownership_default, "
                    "is_system, completeness_rules, created_at, updated_at) "
                    "VALUES (:id, :category_id, :code, :name, :profile_kind, :prefix, "
                    "'pending', false, '{}'::jsonb, now(), now())"
                ),
                {
                    "id": uuid4(),
                    "category_id": category_id,
                    "code": code,
                    "name": name,
                    "profile_kind": profile_kind,
                    "prefix": prefix,
                },
            )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM asset_types "
            "WHERE code IN ('email_service', 'software_service', 'business_environment')"
        )
    )
