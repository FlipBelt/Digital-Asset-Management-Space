"""merge permission and business heads

Revision ID: c95e2b4d8a71
Revises: b24d7f1a6e93, c1d7e6f9a304
Create Date: 2026-08-10 15:42:00.000000
"""

from collections.abc import Sequence


revision: str = "c95e2b4d8a71"
down_revision: str | Sequence[str] | None = ("b24d7f1a6e93", "c1d7e6f9a304")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
