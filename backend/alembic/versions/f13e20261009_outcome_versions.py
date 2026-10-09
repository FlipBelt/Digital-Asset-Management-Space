"""Separate explicit outcome publication from concurrency revisions."""

import sqlalchemy as sa

from alembic import op

revision = "f13e20261009"
down_revision = "f13d20261008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "assets",
        sa.Column(
            "outcome_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "asset_confirmations",
        sa.Column(
            "outcome_version",
            sa.Integer(),
            nullable=True,
        ),
    )
    # Historical revisions do not establish distinct published outcomes. Start at V1;
    # retain every existing revision and confirmation rather than inventing publications.
    op.execute(
        sa.text("""
        UPDATE assets SET outcome_version = 1
        WHERE sharing_scope IS NOT NULL AND (
            confirmed_at IS NOT NULL OR EXISTS (
                SELECT 1 FROM asset_confirmations c
                WHERE c.asset_id = assets.id AND c.consumed_at IS NOT NULL
            )
        )
    """)
    )
    op.execute(
        sa.text("""
        UPDATE asset_confirmations SET outcome_version = 1
        WHERE consumed_at IS NOT NULL
    """)
    )


def downgrade():
    # Code rollback can keep additive columns. Never silently discard live publications.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM assets WHERE outcome_version > 1")):
        raise RuntimeError("Published outcome versions exist; retain schema during code rollback")
    if connection.scalar(
        sa.text("""
        SELECT count(*) FROM asset_confirmations
        WHERE consumed_at IS NULL AND cancelled_at IS NULL AND outcome_version IS NOT NULL
    """)
    ):
        raise RuntimeError("New confirmation previews exist; retain schema during code rollback")
    op.drop_column("asset_confirmations", "outcome_version")
    op.drop_column("assets", "outcome_version")
