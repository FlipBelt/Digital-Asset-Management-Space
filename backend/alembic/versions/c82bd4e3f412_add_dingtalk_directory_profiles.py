"""add DingTalk directory profiles

Revision ID: c82bd4e3f412
Revises: b76fa1c2d301
Create Date: 2026-08-06 13:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c82bd4e3f412"
down_revision: Union[str, Sequence[str], None] = "b76fa1c2d301"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dingtalk_department_links",
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("dingtalk_department_id", sa.String(length=100), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_dingtalk_department_links_department_id_departments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dingtalk_department_links")),
        sa.UniqueConstraint(
            "department_id", name=op.f("uq_dingtalk_department_links_department_id")
        ),
        sa.UniqueConstraint(
            "dingtalk_department_id",
            name=op.f("uq_dingtalk_department_links_dingtalk_department_id"),
        ),
    )
    op.create_table(
        "dingtalk_person_profiles",
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("dingtalk_user_id", sa.String(length=200), nullable=False),
        sa.Column("union_id", sa.String(length=200), nullable=True),
        sa.Column("job_title", sa.String(length=200), nullable=True),
        sa.Column("job_grade", sa.String(length=200), nullable=True),
        sa.Column("profile_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["people.id"], name=op.f("fk_dingtalk_person_profiles_person_id_people")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dingtalk_person_profiles")),
        sa.UniqueConstraint(
            "dingtalk_user_id", name=op.f("uq_dingtalk_person_profiles_dingtalk_user_id")
        ),
        sa.UniqueConstraint("person_id", name=op.f("uq_dingtalk_person_profiles_person_id")),
        sa.UniqueConstraint("union_id", name=op.f("uq_dingtalk_person_profiles_union_id")),
    )


def downgrade() -> None:
    op.drop_table("dingtalk_person_profiles")
    op.drop_table("dingtalk_department_links")
