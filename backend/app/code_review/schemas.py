from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["python", "javascript", "typescript", "java", "c", "cpp"]
Severity = Literal["critical", "high", "medium", "low", "informational"]
Category = Literal[
    "security",
    "bug",
    "performance",
    "reliability",
    "maintainability",
    "code_style",
    "best_practice",
    "type_error",
]


class SourceFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=160)
    content: str = Field(max_length=65_536)


class CreateReviewRequest(BaseModel):
    title: str = Field(default="Code review", min_length=1, max_length=160)
    project_id: UUID | None = None
    language: Language | Literal["auto"] = "auto"
    files: list[SourceFileInput] = Field(min_length=1, max_length=10)
    analyzers: list[str] | None = Field(default=None, max_length=8)
    ai_enabled: bool = True


class FindingStatusUpdate(BaseModel):
    status: Literal["accepted", "dismissed", "fixed"]


class ReviewFeedbackInput(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)


class ApplyPatchInput(BaseModel):
    approved: bool


class AIObservation(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=3000)
    severity: Severity
    category: Category
    file_path: str
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    evidence: str = Field(min_length=1, max_length=1200)
    reasoning: str = Field(min_length=1, max_length=2000)
    recommendation: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)


class AIReviewOutput(BaseModel):
    findings: list[AIObservation] = Field(default_factory=list, max_length=12)


class AIPatchOutput(BaseModel):
    updated_file: str = Field(min_length=1, max_length=65_536)
    explanation: str = Field(min_length=1, max_length=2000)


class ReviewFileOutput(BaseModel):
    path: str
    sha256: str


class AnalyzerStatus(BaseModel):
    analyzer: str
    status: str
    exit_code: int | None = None
    duration_ms: int = 0
    message: str | None = None


class ReviewFindingOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    review_id: str
    file_path: str
    line_start: int | None
    line_end: int | None
    column_start: int | None
    title: str
    description: str
    reasoning: str
    severity: str
    category: str
    evidence: str
    recommendation: str
    suggested_patch: str | None
    source: str
    analyzer: str
    rule_id: str | None
    confidence: float | None
    status: str
    created_at: datetime


class ReviewOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str | None
    title: str
    language: str
    review_status: str
    source_type: str
    summary: str
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    informational_count: int
    execution_duration: int
    configuration: dict
    files: list[ReviewFileOutput] = []
    findings: list[ReviewFindingOutput] = []
    created_at: datetime
    completed_at: datetime | None


class ReviewListOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    language: str
    review_status: str
    project_id: str | None
    summary: str
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    informational_count: int
    execution_duration: int
    created_at: datetime
    completed_at: datetime | None


class ReviewAnalytics(BaseModel):
    total_reviews: int
    total_findings: int
    open_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    informational_count: int
    recent_reviews: list[ReviewListOutput]
    daily_reviews: list[dict]


class PatchPreviewOutput(BaseModel):
    finding_id: str
    file_path: str
    original_sha256: str
    unified_diff: str
    explanation: str
    applied: bool
    rolled_back: bool = False
