from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class AIAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=12000)
    key_points: list[str] = Field(default_factory=list, max_length=20)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    project_id: UUID | None = None


class AIUsageResponse(BaseModel):
    id: str
    project_id: str | None
    provider: str
    model: str
    feature: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: Decimal | None
    status: str
    duration_ms: int
    created_at: datetime


class AIUsageSummary(BaseModel):
    requests: int
    successful_requests: int
    failed_requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: Decimal | None
