"""add usage alerts and DingTalk digest schedules

Revision ID: a6f4c2d8b719
Revises: e7b3d1f8a624
Create Date: 2026-08-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a6f4c2d8b719"
down_revision = "e7b3d1f8a624"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_alert_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("metric_key", sa.String(length=100), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("recipient_person_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_state", sa.String(length=32), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["provider_connection_id"], ["provider_connections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "usage_notification_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("connection_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recipient_person_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("time_of_day", sa.String(length=5), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_sent_on", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "usage_notification_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("usage_alert_rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("usage_notification_schedule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column("message_summary", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["usage_alert_rule_id"], ["usage_alert_rules.id"]),
        sa.ForeignKeyConstraint(["usage_notification_schedule_id"], ["usage_notification_schedules.id"]),
        sa.ForeignKeyConstraint(["provider_connection_id"], ["provider_connections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("usage_notification_logs")
    op.drop_table("usage_notification_schedules")
    op.drop_table("usage_alert_rules")
