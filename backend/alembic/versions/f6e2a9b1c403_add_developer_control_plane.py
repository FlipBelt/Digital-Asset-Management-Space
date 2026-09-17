"""add developer-only sanitized intake control plane

Revision ID: f6e2a9b1c403
Revises: c8d4a2e6f901
Create Date: 2026-08-24
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision = "f6e2a9b1c403"
down_revision = "c8d4a2e6f901"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "developer_intake_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("source_location", sa.String(length=1000), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="staged", nullable=False),
        sa.Column("confidentiality", sa.String(length=32), server_default="developer_only", nullable=False),
        sa.Column("responsible_person_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["responsible_person_id"], ["people.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "developer_intake_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("developer_intake_batch_id", sa.Uuid(), nullable=False),
        sa.Column("record_key", sa.String(length=200), nullable=False),
        sa.Column("source_file", sa.String(length=300), nullable=False),
        sa.Column("suggested_name", sa.String(length=300), nullable=False),
        sa.Column("suggested_layers", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("disposition", sa.String(length=32), server_default="hold", nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("masked_identifiers", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("review_status", sa.String(length=32), server_default="pending_review", nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["developer_intake_batch_id"], ["developer_intake_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("developer_intake_batch_id", "record_key"),
    )
    op.create_index(
        "ix_developer_intake_records_batch_status",
        "developer_intake_records",
        ["developer_intake_batch_id", "review_status"],
    )
    op.execute("""
        INSERT INTO roles (id, code, name, description, created_at, updated_at)
        SELECT gen_random_uuid(), 'developer_supervisor', '开发者控制面', '仅限服务器允许名单中的开发者使用的独立控制面。', now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE code = 'developer_supervisor')
    """)
    op.execute("""
        INSERT INTO user_role_scopes (id, user_id, role_id, scope_type, scope_id, created_at, updated_at)
        SELECT gen_random_uuid(), users.id, roles.id, 'developer', NULL, now(), now()
        FROM users
        JOIN people ON people.id = users.person_id
        JOIN roles ON roles.code = 'developer_supervisor'
        WHERE users.archived_at IS NULL
          AND people.archived_at IS NULL
          AND people.display_name = '十叶-冯硕硕'
          AND NOT EXISTS (
              SELECT 1 FROM user_role_scopes scopes
              WHERE scopes.user_id = users.id AND scopes.role_id = roles.id AND scopes.scope_type = 'developer'
          )
    """)


def downgrade() -> None:
    op.execute("DELETE FROM user_role_scopes WHERE role_id IN (SELECT id FROM roles WHERE code = 'developer_supervisor')")
    op.execute("DELETE FROM roles WHERE code = 'developer_supervisor'")
    op.drop_index("ix_developer_intake_records_batch_status", table_name="developer_intake_records")
    op.drop_table("developer_intake_records")
    op.drop_table("developer_intake_batches")
