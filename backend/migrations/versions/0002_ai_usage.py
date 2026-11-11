"""Persist token and latency metadata for AI calls; prompt content is never stored."""

import sqlalchemy as sa
from alembic import op

revision = "0002_ai_usage"
down_revision = "0001_users_projects_tokens"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("feature", sa.String(length=80), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=14, scale=10), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0",
            name="ck_ai_usage_nonnegative_tokens",
        ),
        sa.CheckConstraint(
            "total_tokens = input_tokens + output_tokens", name="ck_ai_usage_total_tokens"
        ),
        sa.CheckConstraint("duration_ms >= 0", name="ck_ai_usage_duration_nonnegative"),
        sa.CheckConstraint(
            "status IN ('succeeded', 'configuration_error', 'rate_limited', 'timeout', 'provider_error', 'invalid_output')",
            name="ck_ai_usage_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_user_created", "ai_usage", ["user_id", "created_at"])
    op.create_index("ix_ai_usage_project_created", "ai_usage", ["project_id", "created_at"])
    op.create_index("ix_ai_usage_provider_model", "ai_usage", ["provider", "model"])


def downgrade():
    op.drop_index("ix_ai_usage_provider_model", table_name="ai_usage")
    op.drop_index("ix_ai_usage_project_created", table_name="ai_usage")
    op.drop_index("ix_ai_usage_user_created", table_name="ai_usage")
    op.drop_table("ai_usage")
