"""Persist personal bookmarks, evidence and version-bound confirmation."""

import sqlalchemy as sa

from alembic import op

revision = "f13b20260928"
down_revision = "f13a20260924"
branch_labels = None
depends_on = None


def common_columns() -> list:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    # Historical records retain their existing visibility policy; no guessed backfill.
    op.add_column("assets", sa.Column("sharing_scope", sa.String(32), nullable=True))
    op.create_table(
        "asset_bookmarks",
        *common_columns(),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("people.id"), nullable=False),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id"), nullable=False),
        sa.UniqueConstraint("person_id", "asset_id"),
    )
    op.create_table(
        "asset_evidence",
        *common_columns(),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("people.id"), nullable=False),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column(
            "subscription_id", sa.Uuid(), sa.ForeignKey("service_instances.id"), nullable=True
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("observed_effect", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(32), server_default="pending_review", nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
    )
    op.create_index("ix_asset_evidence_person_id", "asset_evidence", ["person_id"])
    op.create_table(
        "asset_confirmations",
        *common_columns(),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("asset_version", sa.Integer(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("result_digest", sa.String(64), nullable=True),
        sa.Column("sharing_scope", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_asset_confirmations_asset_id", "asset_confirmations", ["asset_id"])


def downgrade() -> None:
    db = op.get_bind()
    populated = db.execute(
        sa.text("""
        SELECT EXISTS (SELECT 1 FROM asset_bookmarks)
            OR EXISTS (SELECT 1 FROM asset_evidence)
            OR EXISTS (SELECT 1 FROM asset_confirmations)
            OR EXISTS (SELECT 1 FROM assets WHERE sharing_scope IS NOT NULL)
    """)
    ).scalar()
    if populated:
        raise RuntimeError(
            "Refusing to drop recorded personal facts; restore a verified backup instead."
        )
    op.drop_table("asset_confirmations")
    op.drop_table("asset_evidence")
    op.drop_table("asset_bookmarks")
    op.drop_column("assets", "sharing_scope")
