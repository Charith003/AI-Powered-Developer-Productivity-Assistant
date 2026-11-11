from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Category = Literal["normal", "boundary", "negative", "exception", "regression"]


class PlannedCase(BaseModel):
    target: str = Field(min_length=1, max_length=240)
    objective: str = Field(min_length=1, max_length=1000)
    category: Category
    input_data: str = Field(default="", max_length=1000)
    expected_result: str = Field(default="", max_length=1000)
    expected_exception: str | None = Field(default=None, max_length=240)
    preconditions: str = Field(default="", max_length=500)
    dependencies_or_mocks: list[str] = Field(default_factory=list, max_length=12)
    priority: Literal["low", "medium", "high"] = "medium"


class GeneratedTestOutput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    plan: list[PlannedCase] = Field(min_length=1, max_length=40)
    test_code: str = Field(min_length=1, max_length=65_536)


class GenerateTestsInput(BaseModel):
    project_id: UUID | None = None
    review_finding_id: UUID | None = None
    title: str = Field(default="Generated tests", min_length=1, max_length=160)
    source_path: str = Field(min_length=1, max_length=160)
    source_content: str = Field(min_length=1, max_length=65_536)
    language: Literal["auto", "python"] = "auto"
    framework: str = Field(default="pytest", min_length=1, max_length=32)
    categories: list[Category] = Field(
        default_factory=lambda: ["normal", "boundary", "negative", "exception"],
        min_length=1,
        max_length=5,
    )


class EditGeneratedTestsInput(BaseModel):
    test_code: str = Field(min_length=1, max_length=65_536)


class TestGenerationOutput(BaseModel):
    id: str
    project_id: str | None
    review_finding_id: str | None
    title: str
    language: str
    framework: str
    generation_status: str
    test_plan: list[dict]
    generated_test_content: str
    validation_status: str
    validation_errors: list[str]
    source_path: str
    created_at: datetime
    updated_at: datetime


class ExecutionOutput(BaseModel):
    id: str
    generation_id: str
    source_sha256: str
    test_sha256: str
    execution_status: str
    cancel_requested: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    error_count: int
    line_coverage: float | None
    branch_coverage: float | None
    uncovered_lines: dict[str, list[int]]
    file_coverage: dict[str, dict]
    failure_analysis: list[dict]
    execution_duration: int
    exit_code: int | None
    stdout: str
    stderr: str
    infrastructure_message: str | None
    created_at: datetime
    completed_at: datetime | None


class TestCaseOutput(BaseModel):
    id: str
    test_name: str
    test_file: str
    status: str
    duration: float | None
    error_message: str | None
    traceback: str | None


class CoverageOutput(BaseModel):
    line_coverage: float | None
    branch_coverage: float | None
    uncovered_lines: dict[str, list[int]]
    file_coverage: dict[str, dict]
    available: bool


class FailureExplanation(BaseModel):
    explanations: list["FailureExplanationItem"] = Field(default_factory=list, max_length=50)


class FailureExplanationItem(BaseModel):
    test_name: str = Field(min_length=1, max_length=500)
    error_category: str = Field(min_length=1, max_length=120)
    possible_root_cause: str = Field(min_length=1, max_length=2000)
    suggested_remediation: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)
