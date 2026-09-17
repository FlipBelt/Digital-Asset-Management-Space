"""bind provider usage connections to service instances

Revision ID: d2a7c4e9b511
Revises: c8d4a2e6f901
Create Date: 2026-08-25
"""

from alembic import op
import sqlalchemy as sa


revision = "d2a7c4e9b511"
down_revision = "c8d4a2e6f901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_connections",
        sa.Column("service_instance_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_provider_connections_service_instance_id_service_instances",
        "provider_connections",
        "service_instances",
        ["service_instance_id"],
        ["id"],
    )
    op.create_index(
        "ix_provider_connections_service_instance_id",
        "provider_connections",
        ["service_instance_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_connections_service_instance_id", table_name="provider_connections")
    op.drop_constraint(
        "fk_provider_connections_service_instance_id_service_instances",
        "provider_connections",
        type_="foreignkey",
    )
    op.drop_column("provider_connections", "service_instance_id")
