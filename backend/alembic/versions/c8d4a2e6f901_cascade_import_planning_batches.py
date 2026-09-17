"""cascade import planning records with batches

Revision ID: c8d4a2e6f901
Revises: c64e9b1f2a70
Create Date: 2026-08-18
"""

from alembic import op


revision = "c8d4a2e6f901"
down_revision = "c64e9b1f2a70"
branch_labels = None
depends_on = None


TABLES = (
    "import_analyses",
    "import_proposed_objects",
    "import_proposed_relations",
)


def constraint_name(table: str) -> str:
    return f"fk_{table}_import_batch_id_import_batches"


def upgrade() -> None:
    for table in TABLES:
        op.drop_constraint(constraint_name(table), table, type_="foreignkey")
        op.create_foreign_key(
            constraint_name(table),
            table,
            "import_batches",
            ["import_batch_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(constraint_name(table), table, type_="foreignkey")
        op.create_foreign_key(
            constraint_name(table),
            table,
            "import_batches",
            ["import_batch_id"],
            ["id"],
        )
