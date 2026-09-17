"""allow independently evidenced assets without a legal entity

Revision ID: b4e6d2a9f517
Revises: a1b7c9d2e403
Create Date: 2026-08-25

An L2 registration identity or L6 service may be evidenced before its owning
legal entity is known.  This migration removes only that upstream NOT NULL
constraint; it does not alter existing records or L4 tenant requirements.
"""

import sqlalchemy as sa
from alembic import op


revision = "b4e6d2a9f517"
down_revision = "a1b7c9d2e403"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "assets",
        "legal_entity_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "assets",
        "legal_entity_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
