"""Persist code review runs, source snapshots, findings, feedback and patch events."""

import sqlalchemy as sa
from alembic import op

revision = "0003_code_reviews"
down_revision = "0002_ai_usage"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "code_reviews",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("language", sa.String(24), nullable=False),
        sa.Column("review_status", sa.String(24), nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("total_findings", sa.Integer(), nullable=False),
        sa.Column("critical_count", sa.Integer(), nullable=False),
        sa.Column("high_count", sa.Integer(), nullable=False),
        sa.Column("medium_count", sa.Integer(), nullable=False),
        sa.Column("low_count", sa.Integer(), nullable=False),
        sa.Column("informational_count", sa.Integer(), nullable=False),
        sa.Column("execution_duration", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "review_status IN ('in_progress', 'completed', 'failed')", name="ck_code_reviews_status"
        ),
        sa.CheckConstraint("total_findings >= 0", name="ck_code_reviews_total_findings"),
        sa.CheckConstraint(
            "critical_count >= 0 AND high_count >= 0 AND medium_count >= 0 AND low_count >= 0 AND informational_count >= 0",
            name="ck_code_reviews_nonnegative_counts",
        ),
        sa.CheckConstraint("execution_duration >= 0", name="ck_code_reviews_duration"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_reviews_user_created", "code_reviews", ["user_id", "created_at"])
    op.create_index("ix_code_reviews_project_created", "code_reviews", ["project_id", "created_at"])
    op.create_table(
        "review_files",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("review_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("file_path", sa.String(240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["code_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_review_files_review_path", "review_files", ["review_id", "file_path"], unique=True
    )
    op.create_table(
        "review_findings",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("review_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("file_path", sa.String(240), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("column_start", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("suggested_patch", sa.Text(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("analyzer", sa.String(40), nullable=False),
        sa.Column("rule_id", sa.String(80), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'informational')",
            name="ck_review_findings_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'accepted', 'dismissed', 'fixed')", name="ck_review_findings_status"
        ),
        sa.CheckConstraint("source IN ('static', 'ai')", name="ck_review_findings_source"),
        sa.CheckConstraint(
            "category IN ('security', 'bug', 'performance', 'reliability', 'maintainability', 'code_style', 'best_practice', 'type_error')",
            name="ck_review_findings_category",
        ),
        sa.CheckConstraint(
            "line_start IS NULL OR line_start >= 1", name="ck_review_findings_line_start"
        ),
        sa.CheckConstraint("line_end IS NULL OR line_end >= 1", name="ck_review_findings_line_end"),
        sa.CheckConstraint(
            "line_start IS NULL OR line_end IS NULL OR line_start <= line_end",
            name="ck_review_findings_line_range",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_review_findings_confidence",
        ),
        sa.ForeignKeyConstraint(["review_id"], ["code_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_review_findings_review_severity", "review_findings", ["review_id", "severity"]
    )
    op.create_index("ix_review_findings_review_status", "review_findings", ["review_id", "status"])
    op.create_table(
        "review_feedback",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("review_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_feedback_rating"),
        sa.ForeignKeyConstraint(["review_id"], ["code_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_feedback_review_id", "review_feedback", ["review_id"])
    op.create_table(
        "review_patch_events",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("finding_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("patch", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('previewed', 'applied_to_upload', 'rolled_back')",
            name="ck_review_patch_events_type",
        ),
        sa.ForeignKeyConstraint(["finding_id"], ["review_findings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_patch_events_finding_id", "review_patch_events", ["finding_id"])


def downgrade():
    op.drop_index("ix_review_patch_events_finding_id", table_name="review_patch_events")
    op.drop_table("review_patch_events")
    op.drop_index("ix_review_feedback_review_id", table_name="review_feedback")
    op.drop_table("review_feedback")
    op.drop_index("ix_review_findings_review_status", table_name="review_findings")
    op.drop_index("ix_review_findings_review_severity", table_name="review_findings")
    op.drop_table("review_findings")
    op.drop_index("ix_review_files_review_path", table_name="review_files")
    op.drop_table("review_files")
    op.drop_index("ix_code_reviews_project_created", table_name="code_reviews")
    op.drop_index("ix_code_reviews_user_created", table_name="code_reviews")
    op.drop_table("code_reviews")
