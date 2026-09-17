"""add formal asset assignments and review state

Revision ID: a8e5f4c2d110
Revises: f41d5e9a2c70
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "a8e5f4c2d110"
down_revision: str | Sequence[str] | None = "f41d5e9a2c70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("created_by_person_id", sa.Uuid(), nullable=True))
    op.add_column("assets", sa.Column("confirmed_by_person_id", sa.Uuid(), nullable=True))
    op.add_column("assets", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assets", sa.Column("review_status", sa.String(32), server_default="draft", nullable=False))
    op.create_foreign_key(op.f("fk_assets_created_by_person_id_people"), "assets", "people", ["created_by_person_id"], ["id"])
    op.create_foreign_key(op.f("fk_assets_confirmed_by_person_id_people"), "assets", "people", ["confirmed_by_person_id"], ["id"])
    op.execute("UPDATE assets SET review_status = 'pending_assignment'")
    op.create_index(
        "uq_asset_one_responsible",
        "asset_responsibilities",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("role_type = 'responsible' AND archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_asset_one_responsible", table_name="asset_responsibilities")
    op.drop_constraint(op.f("fk_assets_confirmed_by_person_id_people"), "assets", type_="foreignkey")
    op.drop_constraint(op.f("fk_assets_created_by_person_id_people"), "assets", type_="foreignkey")
    op.drop_column("assets", "review_status")
    op.drop_column("assets", "confirmed_at")
    op.drop_column("assets", "confirmed_by_person_id")
    op.drop_column("assets", "created_by_person_id")
