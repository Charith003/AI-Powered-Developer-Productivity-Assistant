"""Retain bounded raw coverage JSON for execution evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0007_raw_coverage_artifact"
down_revision = "0006_execution_audit_events"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("test_executions", sa.Column("coverage_artifact", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("test_executions", "coverage_artifact")
