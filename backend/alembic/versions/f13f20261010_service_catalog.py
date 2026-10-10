"""Associate services and selectable plans with the unified platform directory."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f13f20261010"
down_revision = "f13e20261009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("service_products", sa.Column("platform_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_service_products_platform_id", "service_products", "platforms", ["platform_id"], ["id"]
    )
    op.add_column(
        "service_products",
        sa.Column("plan_options", postgresql.JSONB(), nullable=False, server_default="[]"),
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM service_products WHERE platform_id IS NOT NULL "
            "OR plan_options <> '[]'::jsonb"
        )
    ):
        raise RuntimeError("Catalog facts exist; retain additive schema during code rollback")
    op.drop_column("service_products", "plan_options")
    op.drop_constraint("fk_service_products_platform_id", "service_products", type_="foreignkey")
    op.drop_column("service_products", "platform_id")
