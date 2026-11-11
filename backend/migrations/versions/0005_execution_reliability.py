"""Add idempotent active-job constraint and cancellation request flag."""

import sqlalchemy as sa
from alembic import op

revision = "0005_execution_reliability"
down_revision = "0004_test_generation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "test_executions",
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Keep the newest active job for each generation and close pre-existing duplicates
    # before applying the partial unique index.
    op.execute(
        sa.text(
            "UPDATE test_executions SET execution_status='infrastructure_failure', "
            "infrastructure_message='Closed duplicate active execution during reliability migration', "
            "completed_at=CURRENT_TIMESTAMP WHERE execution_status IN ('queued', 'running') "
            "AND id IN (SELECT older.id FROM test_executions older JOIN test_executions newer "
            "ON newer.generation_id=older.generation_id "
            "AND newer.execution_status IN ('queued', 'running') "
            "AND (newer.created_at > older.created_at OR "
            "(newer.created_at = older.created_at AND newer.id > older.id)) "
            "WHERE older.execution_status IN ('queued', 'running'))"
        )
    )
    op.create_index(
        "uq_test_executions_active_generation",
        "test_executions",
        ["generation_id"],
        unique=True,
        sqlite_where=sa.text("execution_status IN ('queued', 'running')"),
        postgresql_where=sa.text("execution_status IN ('queued', 'running')"),
    )


def downgrade():
    op.drop_index("uq_test_executions_active_generation", table_name="test_executions")
    op.drop_column("test_executions", "cancel_requested")
