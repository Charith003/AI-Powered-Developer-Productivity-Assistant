"""Persist sanitized test execution lifecycle evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0006_execution_audit_events"
down_revision = "0005_execution_reliability"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "test_execution_events",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("execution_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["test_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_test_execution_events_execution_created",
        "test_execution_events",
        ["execution_id", "created_at"],
    )


def downgrade():
    op.drop_index("ix_test_execution_events_execution_created", table_name="test_execution_events")
    op.drop_table("test_execution_events")
