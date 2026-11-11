"""Persist test generation, isolated execution jobs and case results."""

import sqlalchemy as sa
from alembic import op

revision = "0004_test_generation"
down_revision = "0003_code_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "test_generations",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=False)),
        sa.Column("review_finding_id", sa.Uuid(as_uuid=False)),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("source_path", sa.String(160), nullable=False),
        sa.Column("source_content", sa.Text(), nullable=False),
        sa.Column("language", sa.String(24), nullable=False),
        sa.Column("framework", sa.String(32), nullable=False),
        sa.Column("generation_status", sa.String(24), nullable=False),
        sa.Column("test_plan", sa.JSON(), nullable=False),
        sa.Column("generated_test_content", sa.Text(), nullable=False),
        sa.Column("validation_status", sa.String(24), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("ai_model", sa.String(120)),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("language IN ('python')", name="ck_test_generations_language"),
        sa.CheckConstraint("framework IN ('pytest')", name="ck_test_generations_framework"),
        sa.CheckConstraint(
            "generation_status IN ('completed', 'failed')", name="ck_test_generations_status"
        ),
        sa.CheckConstraint(
            "validation_status IN ('unvalidated', 'valid', 'invalid')",
            name="ck_test_generations_validation",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["review_finding_id"], ["review_findings.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_test_generations_user_created", "test_generations", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_test_generations_project_created", "test_generations", ["project_id", "created_at"]
    )
    op.create_table(
        "test_executions",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("generation_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("test_code_snapshot", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("test_sha256", sa.String(64), nullable=False),
        sa.Column("execution_status", sa.String(32), nullable=False),
        sa.Column("total_tests", sa.Integer(), nullable=False),
        sa.Column("passed_tests", sa.Integer(), nullable=False),
        sa.Column("failed_tests", sa.Integer(), nullable=False),
        sa.Column("skipped_tests", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("line_coverage", sa.Float()),
        sa.Column("branch_coverage", sa.Float()),
        sa.Column("uncovered_lines", sa.JSON(), nullable=False),
        sa.Column("file_coverage", sa.JSON(), nullable=False),
        sa.Column("failure_analysis", sa.JSON(), nullable=False),
        sa.Column("execution_duration", sa.Integer(), nullable=False),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("stdout", sa.Text(), nullable=False),
        sa.Column("stderr", sa.Text(), nullable=False),
        sa.Column("infrastructure_message", sa.String(500)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "execution_status IN ('queued', 'running', 'completed', 'failed', 'error', 'timed_out', 'cancelled', 'infrastructure_failure')",
            name="ck_test_executions_status",
        ),
        sa.CheckConstraint(
            "total_tests >= 0 AND passed_tests >= 0 AND failed_tests >= 0 AND skipped_tests >= 0 AND error_count >= 0",
            name="ck_test_executions_counts",
        ),
        sa.CheckConstraint("execution_duration >= 0", name="ck_test_executions_duration"),
        sa.ForeignKeyConstraint(["generation_id"], ["test_generations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_test_executions_generation_created", "test_executions", ["generation_id", "created_at"]
    )
    op.create_index(
        "ix_test_executions_status_created", "test_executions", ["execution_status", "created_at"]
    )
    op.create_table(
        "test_case_results",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("execution_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("test_name", sa.String(500), nullable=False),
        sa.Column("test_file", sa.String(240), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("duration", sa.Float()),
        sa.Column("error_message", sa.Text()),
        sa.Column("traceback", sa.Text()),
        sa.ForeignKeyConstraint(["execution_id"], ["test_executions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_test_case_results_execution", "test_case_results", ["execution_id"])


def downgrade():
    op.drop_index("ix_test_case_results_execution", table_name="test_case_results")
    op.drop_table("test_case_results")
    op.drop_index("ix_test_executions_status_created", table_name="test_executions")
    op.drop_index("ix_test_executions_generation_created", table_name="test_executions")
    op.drop_table("test_executions")
    op.drop_index("ix_test_generations_project_created", table_name="test_generations")
    op.drop_index("ix_test_generations_user_created", table_name="test_generations")
    op.drop_table("test_generations")
