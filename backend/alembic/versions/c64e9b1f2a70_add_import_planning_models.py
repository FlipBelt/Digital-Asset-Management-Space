"""add import planning models

Revision ID: c64e9b1f2a70
Revises: b92d3e71a4f6
Create Date: 2026-08-18
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c64e9b1f2a70"
down_revision = "b92d3e71a4f6"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "import_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_mode", sa.String(length=32), server_default="rules", nullable=False),
        sa.Column("analyzer_version", sa.String(length=50), nullable=False),
        sa.Column("catalog_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="completed", nullable=False),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_import_analyses_batch_created", "import_analyses", ["import_batch_id", "created_at"]
    )

    op.create_table(
        "import_proposed_objects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("source_import_record_id", sa.Uuid(), nullable=True),
        sa.Column("proposal_key", sa.String(length=200), nullable=False),
        sa.Column("layer_code", sa.String(length=32), nullable=False),
        sa.Column("object_type", sa.String(length=80), nullable=False),
        sa.Column("suggested_name", sa.String(length=300), nullable=False),
        sa.Column(
            "normalized_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("extraction_confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column(
            "match_confidence", sa.Numeric(precision=5, scale=4), server_default="0", nullable=False
        ),
        sa.Column("match_status", sa.String(length=32), server_default="new", nullable=False),
        sa.Column(
            "review_status", sa.String(length=32), server_default="pending_review", nullable=False
        ),
        sa.Column("matched_asset_id", sa.Uuid(), nullable=True),
        sa.Column("matched_platform_id", sa.Uuid(), nullable=True),
        sa.Column("matched_person_id", sa.Uuid(), nullable=True),
        sa.Column("matched_department_id", sa.Uuid(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_import_record_id"], ["source_import_records.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["matched_asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["matched_platform_id"], ["platforms.id"]),
        sa.ForeignKeyConstraint(["matched_person_id"], ["people.id"]),
        sa.ForeignKeyConstraint(["matched_department_id"], ["departments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_batch_id", "proposal_key"),
    )
    op.create_index(
        "ix_import_proposed_objects_batch_status",
        "import_proposed_objects",
        ["import_batch_id", "review_status"],
    )
    op.create_index(
        "ix_import_proposed_objects_match",
        "import_proposed_objects",
        ["matched_asset_id", "matched_person_id"],
    )

    op.create_table(
        "import_proposed_relations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("source_proposal_id", sa.Uuid(), nullable=False),
        sa.Column("target_proposal_id", sa.Uuid(), nullable=False),
        sa.Column("relation_type", sa.String(length=50), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column(
            "validation_status", sa.String(length=32), server_default="pending", nullable=False
        ),
        sa.Column(
            "review_status", sa.String(length=32), server_default="pending_review", nullable=False
        ),
        sa.Column("review_note", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_proposal_id"], ["import_proposed_objects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_proposal_id"], ["import_proposed_objects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_batch_id",
            "source_proposal_id",
            "target_proposal_id",
            "relation_type",
            name="uq_import_proposed_relation",
        ),
    )
    op.create_index(
        "ix_import_proposed_relations_batch_status",
        "import_proposed_relations",
        ["import_batch_id", "review_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_import_proposed_relations_batch_status", table_name="import_proposed_relations"
    )
    op.drop_table("import_proposed_relations")
    op.drop_index("ix_import_proposed_objects_match", table_name="import_proposed_objects")
    op.drop_index("ix_import_proposed_objects_batch_status", table_name="import_proposed_objects")
    op.drop_table("import_proposed_objects")
    op.drop_index("ix_import_analyses_batch_created", table_name="import_analyses")
    op.drop_table("import_analyses")
