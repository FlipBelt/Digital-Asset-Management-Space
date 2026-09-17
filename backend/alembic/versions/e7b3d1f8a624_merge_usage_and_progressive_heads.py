"""merge usage monitoring and progressive-entry heads

Revision ID: e7b3d1f8a624
Revises: b4e6d2a9f517, d2a7c4e9b511
Create Date: 2026-08-25
"""

from collections.abc import Sequence


revision: str = "e7b3d1f8a624"
down_revision: str | Sequence[str] | None = ("b4e6d2a9f517", "d2a7c4e9b511")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
