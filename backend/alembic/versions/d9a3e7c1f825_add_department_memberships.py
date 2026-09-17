"""add department memberships for DingTalk organization tree

Revision ID: d9a3e7c1f825
Revises: c82bd4e3f412
Create Date: 2026-08-06 14:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9a3e7c1f825"
down_revision: Union[str, Sequence[str], None] = "c82bd4e3f412"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "department_memberships",
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("is_manager", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_department_memberships_department_id_departments"),
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["people.id"], name=op.f("fk_department_memberships_person_id_people")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_department_memberships")),
        sa.UniqueConstraint("person_id", "department_id", name="uq_department_memberships_person_id"),
    )


def downgrade() -> None:
    op.drop_table("department_memberships")
