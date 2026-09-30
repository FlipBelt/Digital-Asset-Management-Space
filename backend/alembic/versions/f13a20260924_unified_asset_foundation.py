"""Unified asset foundation; preserve historical workflow classifications."""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "f13a20260924"
down_revision = "b8c4d2e6f901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, size in [
        ("source_system", 120),
        ("source_agent", 120),
        ("source_reference", 500),
        ("development_method", 32),
    ]:
        op.add_column("assets", sa.Column(name, sa.String(size), nullable=True))
    for name, size in [("funding_source", 32), ("usage_frequency", 32), ("primary_purpose", 500)]:
        op.add_column("service_instances", sa.Column(name, sa.String(size), nullable=True))
    op.add_column("service_instances", sa.Column("payer_person_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_service_instances_payer", "service_instances", "people", ["payer_person_id"], ["id"]
    )
    # Existing values remain unknown, not incorrectly backfilled as company-funded.
    db = op.get_bind()
    category = db.execute(
        sa.text(
            "SELECT id FROM asset_categories WHERE code='internal_system' AND archived_at IS NULL"
        )
    ).scalar()
    if category is None:
        category = uuid.uuid4()
        db.execute(
            sa.text(
                "INSERT INTO asset_categories "
                "(id, code, name, sort_order, created_at, updated_at) "
                "VALUES (:id, 'internal_system', '系统与 AI 能力', 20, now(), now())"
            ),
            {"id": category},
        )
    for code, name in [
        ("ai_skill", "AI 技能"),
        ("ai_plugin", "AI 插件"),
        ("ai_agent", "AI 智能体"),
    ]:
        db.execute(
            sa.text("""INSERT INTO asset_types
            (id, category_id, code, name, profile_kind, code_prefix, ownership_default,
             is_system, completeness_rules, created_at, updated_at)
            SELECT :id, :category, CAST(:code AS varchar(80)), :name,
                   'generic', 'AI', 'manual', true, '{}', now(), now()
            WHERE NOT EXISTS (SELECT 1 FROM asset_types WHERE code=CAST(:code AS varchar(80)))"""),
            {"id": uuid.uuid4(), "category": category, "code": code, "name": name},
        )


def downgrade() -> None:
    db = op.get_bind()
    if db.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM assets WHERE source_system IS NOT NULL "
            "OR source_agent IS NOT NULL "
            "OR source_reference IS NOT NULL OR development_method IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM service_instances WHERE payer_person_id IS NOT NULL "
            "OR funding_source IS NOT NULL OR usage_frequency IS NOT NULL "
            "OR primary_purpose IS NOT NULL)"
        )
    ).scalar():
        raise RuntimeError(
            "Refusing to drop recorded source/subscription facts; restore a verified backup."
        )
    # Keep catalog entries and user assets: rolling back the UI must not delete facts.
    op.drop_constraint("fk_service_instances_payer", "service_instances", type_="foreignkey")
    for name in ["payer_person_id", "funding_source", "usage_frequency", "primary_purpose"]:
        op.drop_column("service_instances", name)
    for name in ["source_system", "source_agent", "source_reference", "development_method"]:
        op.drop_column("assets", name)
