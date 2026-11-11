from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.ai.schemas import AIAnswer, AIUsageResponse, AIUsageSummary, GenerateRequest
from app.ai.service import AIService
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import AIUsage, Project, User

router = APIRouter(prefix="/api/v1/ai", tags=["AI provider"])


def assert_owned_project(project_id: UUID | None, user: User, db: Session) -> str | None:
    if project_id is None:
        return None
    exists = db.scalar(
        select(Project.id).where(Project.id == str(project_id), Project.owner_id == user.id)
    )
    if exists is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return str(project_id)


def status_payload() -> dict[str, str | bool | None]:
    provider = settings.ai_provider.lower()
    configured = provider == "openai" and bool(settings.openai_api_key)
    if provider != "openai":
        message = (
            f"AI provider '{settings.ai_provider}' is not supported. Configure AI_PROVIDER=openai."
        )
    elif not settings.openai_api_key:
        message = "AI is not configured. Set OPENAI_API_KEY on the backend, then restart the API."
    else:
        message = None
    return {
        "provider": settings.ai_provider,
        "model": settings.openai_model,
        "embedding_model": settings.openai_embedding_model,
        "api_key_configured": bool(settings.openai_api_key),
        "available": configured,
        "message": message,
    }


@router.get("/status")
def ai_status(user: User = Depends(get_current_user)) -> dict[str, str | bool | None]:
    return status_payload()


@router.post("/generate", response_model=AIAnswer)
async def generate(
    payload: GenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIAnswer:
    project_id = assert_owned_project(payload.project_id, user, db)
    answer, _ = await AIService(db, settings).generate_answer(
        user_id=user.id, project_id=project_id, prompt=payload.prompt
    )
    return answer


def usage_query(user: User, db: Session, project_id: UUID | None):
    query = select(AIUsage).where(AIUsage.user_id == user.id)
    if project_id is not None:
        owned_id = assert_owned_project(project_id, user, db)
        query = query.where(AIUsage.project_id == owned_id)
    return query


@router.get("/usage", response_model=list[AIUsageResponse])
def list_usage(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    project_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AIUsage]:
    query = usage_query(user, db, project_id).order_by(AIUsage.created_at.desc(), AIUsage.id.desc())
    return list(db.scalars(query.limit(limit).offset(offset)))


@router.get("/usage/summary", response_model=AIUsageSummary)
def usage_summary(
    project_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int | str | None]:
    query = usage_query(user, db, project_id).with_only_columns(
        func.count(AIUsage.id).label("requests"),
        func.coalesce(func.sum(case((AIUsage.status == "succeeded", 1), else_=0)), 0).label(
            "successful_requests"
        ),
        func.coalesce(func.sum(case((AIUsage.status != "succeeded", 1), else_=0)), 0).label(
            "failed_requests"
        ),
        func.coalesce(func.sum(AIUsage.input_tokens), 0).label("input_tokens"),
        func.coalesce(func.sum(AIUsage.output_tokens), 0).label("output_tokens"),
        func.coalesce(func.sum(AIUsage.total_tokens), 0).label("total_tokens"),
        func.sum(AIUsage.estimated_cost_usd).label("estimated_cost_usd"),
    )
    row = db.execute(query).one()
    cost: Decimal | None = row.estimated_cost_usd
    return {
        "requests": row.requests,
        "successful_requests": row.successful_requests,
        "failed_requests": row.failed_requests,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "total_tokens": row.total_tokens,
        "estimated_cost_usd": str(cost) if cost is not None else None,
    }
