"""remove unused DingTalk job grade field

Revision ID: ea42c8b6f190
Revises: d9a3e7c1f825
Create Date: 2026-08-06 14:25:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ea42c8b6f190"
down_revision: Union[str, Sequence[str], None] = "d9a3e7c1f825"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("dingtalk_person_profiles", "job_grade")


def downgrade() -> None:
    op.add_column("dingtalk_person_profiles", sa.Column("job_grade", sa.String(length=200)))
