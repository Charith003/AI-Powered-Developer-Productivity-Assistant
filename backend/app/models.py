from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    repository_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    owner: Mapped[User] = relationship(back_populates="projects")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class AIUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0",
            name="ck_ai_usage_nonnegative_tokens",
        ),
        CheckConstraint(
            "total_tokens = input_tokens + output_tokens", name="ck_ai_usage_total_tokens"
        ),
        CheckConstraint("duration_ms >= 0", name="ck_ai_usage_duration_nonnegative"),
        CheckConstraint(
            "status IN ('succeeded', 'configuration_error', 'rate_limited', 'timeout', 'provider_error', 'invalid_output')",
            name="ck_ai_usage_status",
        ),
        Index("ix_ai_usage_user_created", "user_id", "created_at"),
        Index("ix_ai_usage_project_created", "project_id", "created_at"),
        Index("ix_ai_usage_provider_model", "provider", "model"),
    )

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    feature: Mapped[str] = mapped_column(String(80), nullable=False)
    input_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 10), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class CodeReview(Base):
    __tablename__ = "code_reviews"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('in_progress', 'completed', 'failed')",
            name="ck_code_reviews_status",
        ),
        CheckConstraint("total_findings >= 0", name="ck_code_reviews_total_findings"),
        CheckConstraint(
            "critical_count >= 0 AND high_count >= 0 AND medium_count >= 0 AND low_count >= 0 AND informational_count >= 0",
            name="ck_code_reviews_nonnegative_counts",
        ),
        CheckConstraint("execution_duration >= 0", name="ck_code_reviews_duration"),
        Index("ix_code_reviews_user_created", "user_id", "created_at"),
        Index("ix_code_reviews_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    language: Mapped[str] = mapped_column(String(24), nullable=False)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="in_progress")
    source_type: Mapped[str] = mapped_column(String(24), nullable=False, default="uploaded")
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    total_findings: Mapped[int] = mapped_column(default=0, nullable=False)
    critical_count: Mapped[int] = mapped_column(default=0, nullable=False)
    high_count: Mapped[int] = mapped_column(default=0, nullable=False)
    medium_count: Mapped[int] = mapped_column(default=0, nullable=False)
    low_count: Mapped[int] = mapped_column(default=0, nullable=False)
    informational_count: Mapped[int] = mapped_column(default=0, nullable=False)
    execution_duration: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewFile(Base):
    __tablename__ = "review_files"
    __table_args__ = (Index("ix_review_files_review_path", "review_id", "file_path", unique=True),)
    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    review_id: Mapped[str] = mapped_column(
        ForeignKey("code_reviews.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(240), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ReviewFinding(Base):
    __tablename__ = "review_findings"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'informational')",
            name="ck_review_findings_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'accepted', 'dismissed', 'fixed')",
            name="ck_review_findings_status",
        ),
        CheckConstraint("source IN ('static', 'ai')", name="ck_review_findings_source"),
        CheckConstraint(
            "category IN ('security', 'bug', 'performance', 'reliability', 'maintainability', 'code_style', 'best_practice', 'type_error')",
            name="ck_review_findings_category",
        ),
        CheckConstraint(
            "line_start IS NULL OR line_start >= 1", name="ck_review_findings_line_start"
        ),
        CheckConstraint("line_end IS NULL OR line_end >= 1", name="ck_review_findings_line_end"),
        CheckConstraint(
            "line_start IS NULL OR line_end IS NULL OR line_start <= line_end",
            name="ck_review_findings_line_range",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_review_findings_confidence",
        ),
        Index("ix_review_findings_review_severity", "review_id", "severity"),
        Index("ix_review_findings_review_status", "review_id", "status"),
    )
    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    review_id: Mapped[str] = mapped_column(
        ForeignKey("code_reviews.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(240), nullable=False)
    line_start: Mapped[int | None] = mapped_column(nullable=True)
    line_end: Mapped[int | None] = mapped_column(nullable=True)
    column_start: Mapped[int | None] = mapped_column(nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recommendation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    suggested_patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    analyzer: Mapped[str] = mapped_column(String(40), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ReviewFeedback(Base):
    __tablename__ = "review_feedback"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_feedback_rating"),)
    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    review_id: Mapped[str] = mapped_column(
        ForeignKey("code_reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[int] = mapped_column(nullable=False)
    comment: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewPatchEvent(Base):
    __tablename__ = "review_patch_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('previewed', 'applied_to_upload', 'rolled_back')",
            name="ck_review_patch_events_type",
        ),
    )
    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    finding_id: Mapped[str] = mapped_column(
        ForeignKey("review_findings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    patch: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TestGeneration(Base):
    __tablename__ = "test_generations"
    __table_args__ = (
        CheckConstraint("language IN ('python')", name="ck_test_generations_language"),
        CheckConstraint("framework IN ('pytest')", name="ck_test_generations_framework"),
        CheckConstraint(
            "generation_status IN ('completed', 'failed')", name="ck_test_generations_status"
        ),
        CheckConstraint(
            "validation_status IN ('unvalidated', 'valid', 'invalid')",
            name="ck_test_generations_validation",
        ),
        Index("ix_test_generations_user_created", "user_id", "created_at"),
        Index("ix_test_generations_project_created", "project_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    review_finding_id: Mapped[str | None] = mapped_column(
        ForeignKey("review_findings.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    source_path: Mapped[str] = mapped_column(String(160), nullable=False)
    source_content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(24), nullable=False)
    framework: Mapped[str] = mapped_column(String(32), nullable=False)
    generation_status: Mapped[str] = mapped_column(String(24), nullable=False)
    test_plan: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    generated_test_content: Mapped[str] = mapped_column(Text, nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unvalidated"
    )
    validation_errors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ai_model: Mapped[str | None] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class TestExecution(Base):
    __tablename__ = "test_executions"
    __table_args__ = (
        CheckConstraint(
            "execution_status IN ('queued', 'running', 'completed', 'failed', 'error', 'timed_out', 'cancelled', 'infrastructure_failure')",
            name="ck_test_executions_status",
        ),
        CheckConstraint(
            "total_tests >= 0 AND passed_tests >= 0 AND failed_tests >= 0 AND skipped_tests >= 0 AND error_count >= 0",
            name="ck_test_executions_counts",
        ),
        CheckConstraint("execution_duration >= 0", name="ck_test_executions_duration"),
        Index("ix_test_executions_generation_created", "generation_id", "created_at"),
        Index("ix_test_executions_status_created", "execution_status", "created_at"),
        Index(
            "uq_test_executions_active_generation",
            "generation_id",
            unique=True,
            sqlite_where=text("execution_status IN ('queued', 'running')"),
            postgresql_where=text("execution_status IN ('queued', 'running')"),
        ),
    )
    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    generation_id: Mapped[str] = mapped_column(
        ForeignKey("test_generations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    test_code_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    test_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    execution_status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    total_tests: Mapped[int] = mapped_column(default=0, nullable=False)
    passed_tests: Mapped[int] = mapped_column(default=0, nullable=False)
    failed_tests: Mapped[int] = mapped_column(default=0, nullable=False)
    skipped_tests: Mapped[int] = mapped_column(default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(default=0, nullable=False)
    line_coverage: Mapped[float | None] = mapped_column(nullable=True)
    branch_coverage: Mapped[float | None] = mapped_column(nullable=True)
    uncovered_lines: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    file_coverage: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    coverage_artifact: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_analysis: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    execution_duration: Mapped[int] = mapped_column(default=0, nullable=False)
    exit_code: Mapped[int | None] = mapped_column(nullable=True)
    stdout: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stderr: Mapped[str] = mapped_column(Text, nullable=False, default="")
    infrastructure_message: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class TestCaseResult(Base):
    __tablename__ = "test_case_results"
    __table_args__ = (Index("ix_test_case_results_execution", "execution_id"),)
    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("test_executions.id", ondelete="CASCADE"), nullable=False
    )
    test_name: Mapped[str] = mapped_column(String(500), nullable=False)
    test_file: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    duration: Mapped[float | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    traceback: Mapped[str | None] = mapped_column(Text)


class TestExecutionEvent(Base):
    __tablename__ = "test_execution_events"
    __table_args__ = (
        Index("ix_test_execution_events_execution_created", "execution_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("test_executions.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
