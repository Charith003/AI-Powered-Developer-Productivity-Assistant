import difflib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, exists, func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.code_review.schemas import (
    ApplyPatchInput,
    CreateReviewRequest,
    FindingStatusUpdate,
    PatchPreviewOutput,
    ReviewAnalytics,
    ReviewFeedbackInput,
    ReviewFindingOutput,
    ReviewListOutput,
    ReviewOutput,
)
from app.code_review.service import CodeReviewService
from app.code_review.validators import sha256
from app.config import settings
from app.database import get_db
from app.models import (
    CodeReview,
    Project,
    ReviewFeedback,
    ReviewFile,
    ReviewFinding,
    ReviewPatchEvent,
    User,
)

router = APIRouter(prefix="/api/v1/reviews", tags=["code reviews"])


def owned_review(review_id: UUID, user: User, db: Session) -> CodeReview:
    review = db.scalar(
        select(CodeReview).where(CodeReview.id == str(review_id), CodeReview.user_id == user.id)
    )
    if review is None:
        raise HTTPException(404, "Review not found")
    return review


def review_output(review: CodeReview, db: Session) -> dict:
    files = list(db.scalars(select(ReviewFile).where(ReviewFile.review_id == review.id)))
    findings = list(
        db.scalars(
            select(ReviewFinding)
            .where(ReviewFinding.review_id == review.id)
            .order_by(ReviewFinding.file_path, ReviewFinding.line_start, ReviewFinding.created_at)
        )
    )
    return {
        "id": review.id,
        "project_id": review.project_id,
        "title": review.title,
        "language": review.language,
        "review_status": review.review_status,
        "source_type": review.source_type,
        "summary": review.summary,
        "total_findings": review.total_findings,
        "critical_count": review.critical_count,
        "high_count": review.high_count,
        "medium_count": review.medium_count,
        "low_count": review.low_count,
        "informational_count": review.informational_count,
        "execution_duration": review.execution_duration,
        "configuration": review.configuration,
        "files": [{"path": item.file_path, "sha256": item.sha256} for item in files],
        "findings": [ReviewFindingOutput.model_validate(item).model_dump() for item in findings],
        "created_at": review.created_at,
        "completed_at": review.completed_at,
    }


@router.get("/summary", response_model=ReviewAnalytics)
def review_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review_stats = db.execute(
        select(
            func.count(CodeReview.id), func.coalesce(func.sum(CodeReview.total_findings), 0)
        ).where(CodeReview.user_id == user.id)
    ).one()
    finding_stats = db.execute(
        select(
            func.coalesce(func.sum(case((ReviewFinding.status == "open", 1), else_=0)), 0),
            func.coalesce(func.sum(case((ReviewFinding.severity == "critical", 1), else_=0)), 0),
            func.coalesce(func.sum(case((ReviewFinding.severity == "high", 1), else_=0)), 0),
            func.coalesce(func.sum(case((ReviewFinding.severity == "medium", 1), else_=0)), 0),
            func.coalesce(func.sum(case((ReviewFinding.severity == "low", 1), else_=0)), 0),
            func.coalesce(
                func.sum(case((ReviewFinding.severity == "informational", 1), else_=0)), 0
            ),
        )
        .join(CodeReview, CodeReview.id == ReviewFinding.review_id)
        .where(CodeReview.user_id == user.id)
    ).one()
    now = datetime.now(UTC)
    since = now - timedelta(days=6)
    recent = list(
        db.scalars(
            select(CodeReview)
            .where(CodeReview.user_id == user.id)
            .order_by(CodeReview.created_at.desc())
            .limit(5)
        )
    )
    dates = db.scalars(
        select(CodeReview.created_at).where(
            CodeReview.user_id == user.id, CodeReview.created_at >= since
        )
    )
    counts = {}
    for created_at in dates:
        day = created_at.date().isoformat()
        counts[day] = counts.get(day, 0) + 1
    daily = [
        {
            "date": (since.date() + timedelta(days=index)).isoformat(),
            "count": counts.get((since.date() + timedelta(days=index)).isoformat(), 0),
        }
        for index in range(7)
    ]
    return {
        "total_reviews": review_stats[0],
        "total_findings": review_stats[1],
        "open_findings": finding_stats[0],
        "critical_count": finding_stats[1],
        "high_count": finding_stats[2],
        "medium_count": finding_stats[3],
        "low_count": finding_stats[4],
        "informational_count": finding_stats[5],
        "recent_reviews": recent,
        "daily_reviews": daily,
    }


@router.post("", response_model=ReviewOutput, status_code=201)
async def create_review(
    payload: CreateReviewRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.project_id is not None:
        project = db.scalar(
            select(Project.id).where(
                Project.id == str(payload.project_id), Project.owner_id == user.id
            )
        )
        if project is None:
            raise HTTPException(404, "Project not found")
    review = await CodeReviewService(db, settings).analyze_code(user_id=user.id, payload=payload)
    return review_output(review, db)


@router.get("", response_model=list[ReviewListOutput])
def list_reviews(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=160),
    project_id: UUID | None = None,
    language: str | None = None,
    review_status: str | None = None,
    severity: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(CodeReview).where(CodeReview.user_id == user.id)
    if project_id is not None:
        query = query.where(CodeReview.project_id == str(project_id))
    if language:
        query = query.where(CodeReview.language == language.lower())
    if review_status:
        query = query.where(CodeReview.review_status == review_status)
    if search:
        query = query.where(CodeReview.title.ilike(f"%{search.strip()}%"))
    if created_from:
        query = query.where(CodeReview.created_at >= created_from)
    if created_to:
        query = query.where(CodeReview.created_at <= created_to)
    if severity:
        query = query.where(
            exists(
                select(ReviewFinding.id).where(
                    ReviewFinding.review_id == CodeReview.id,
                    ReviewFinding.severity == severity.lower(),
                )
            )
        )
    return list(
        db.scalars(query.order_by(CodeReview.created_at.desc()).limit(limit).offset(offset))
    )


@router.get("/{review_id}", response_model=ReviewOutput)
def get_review(
    review_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return review_output(owned_review(review_id, user, db), db)


@router.get("/{review_id}/findings", response_model=list[ReviewFindingOutput])
def list_findings(
    review_id: UUID,
    severity: str | None = None,
    category: str | None = None,
    file_path: str | None = Query(default=None, max_length=240),
    analyzer: str | None = None,
    status: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = owned_review(review_id, user, db)
    query = select(ReviewFinding).where(ReviewFinding.review_id == review.id)
    if severity:
        query = query.where(ReviewFinding.severity == severity.lower())
    if category:
        query = query.where(ReviewFinding.category == category.lower())
    if file_path:
        query = query.where(ReviewFinding.file_path == file_path)
    if analyzer:
        query = query.where(ReviewFinding.analyzer == analyzer.lower())
    if status:
        query = query.where(ReviewFinding.status == status.lower())
    return list(
        db.scalars(query.order_by(ReviewFinding.file_path, ReviewFinding.line_start).limit(500))
    )


def owned_finding(review: CodeReview, finding_id: UUID, db: Session) -> ReviewFinding:
    finding = db.scalar(
        select(ReviewFinding).where(
            ReviewFinding.id == str(finding_id), ReviewFinding.review_id == review.id
        )
    )
    if finding is None:
        raise HTTPException(404, "Finding not found")
    return finding


@router.patch("/{review_id}/findings/{finding_id}", response_model=ReviewFindingOutput)
def update_finding(
    review_id: UUID,
    finding_id: UUID,
    payload: FindingStatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = owned_review(review_id, user, db)
    finding = owned_finding(review, finding_id, db)
    allowed = {
        "open": {"accepted", "dismissed", "fixed"},
        "accepted": {"open", "dismissed", "fixed"},
        "dismissed": {"open", "accepted", "fixed"},
        "fixed": {"open"},
    }
    if payload.status != finding.status and payload.status not in allowed[finding.status]:
        raise HTTPException(409, "Finding status transition is not allowed")
    finding.status = payload.status
    db.commit()
    db.refresh(finding)
    return finding


@router.post("/{review_id}/findings/{finding_id}/patch", response_model=PatchPreviewOutput)
async def generate_patch(
    review_id: UUID,
    finding_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = owned_review(review_id, user, db)
    try:
        review, finding, source, patch, updated, explanation = await CodeReviewService(
            db, settings
        ).generate_patch(
            user_id=user.id,
            review_id=review.id,
            finding_id=str(finding_id),
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409 if "changed since" in str(exc) else 422, str(exc)) from exc
    payload = json.dumps(
        {"diff": patch, "updated_content": updated, "expected_sha256": source.sha256},
        ensure_ascii=False,
    )
    finding.suggested_patch = patch
    db.add(
        ReviewPatchEvent(
            finding_id=finding.id,
            user_id=user.id,
            event_type="previewed",
            patch=payload,
        )
    )
    db.commit()
    return PatchPreviewOutput(
        finding_id=finding.id,
        file_path=source.file_path,
        original_sha256=source.sha256,
        unified_diff=patch,
        explanation=explanation,
        applied=False,
    )


@router.post("/{review_id}/findings/{finding_id}/patch/apply", response_model=PatchPreviewOutput)
def apply_patch(
    review_id: UUID,
    finding_id: UUID,
    payload: ApplyPatchInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.approved:
        raise HTTPException(400, "Explicit approval is required before applying a patch")
    review = owned_review(review_id, user, db)
    finding = owned_finding(review, finding_id, db)
    source = db.scalar(
        select(ReviewFile).where(
            ReviewFile.review_id == review.id, ReviewFile.file_path == finding.file_path
        )
    )
    event = db.scalar(
        select(ReviewPatchEvent)
        .where(
            ReviewPatchEvent.finding_id == finding.id, ReviewPatchEvent.event_type == "previewed"
        )
        .order_by(ReviewPatchEvent.created_at.desc())
    )
    if source is None or event is None:
        raise HTTPException(409, "Generate a patch preview before applying")
    try:
        patch_payload = json.loads(event.patch)
    except json.JSONDecodeError as exc:
        raise HTTPException(409, "Patch preview is invalid") from exc
    if sha256(source.content) != patch_payload.get("expected_sha256"):
        raise HTTPException(409, "Uploaded source changed since this patch was generated")
    diff = patch_payload.get("diff", "")
    if (
        not diff.startswith(f"--- a/{source.file_path}\n")
        or f"+++ b/{source.file_path}\n" not in diff
    ):
        raise HTTPException(422, "Patch path validation failed")
    new_content = patch_payload.get("updated_content")
    if (
        not isinstance(new_content, str)
        or len(new_content.encode("utf-8")) > 65_536
        or "\x00" in new_content
    ):
        raise HTTPException(422, "Patch content validation failed")
    original_content = source.content
    source.content = new_content
    source.sha256 = sha256(new_content)
    finding.status = "fixed"
    db.add(
        ReviewPatchEvent(
            finding_id=finding.id,
            user_id=user.id,
            event_type="applied_to_upload",
            patch=json.dumps(
                {
                    "diff": diff,
                    "original_content": original_content,
                    "applied_sha256": sha256(new_content),
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    return PatchPreviewOutput(
        finding_id=finding.id,
        file_path=source.file_path,
        original_sha256=patch_payload["expected_sha256"],
        unified_diff=diff,
        explanation="Approved patch applied to the stored uploaded source snapshot only.",
        applied=True,
    )


@router.post("/{review_id}/findings/{finding_id}/patch/rollback", response_model=PatchPreviewOutput)
def rollback_patch(
    review_id: UUID,
    finding_id: UUID,
    payload: ApplyPatchInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.approved:
        raise HTTPException(400, "Explicit rollback approval is required")
    review = owned_review(review_id, user, db)
    finding = owned_finding(review, finding_id, db)
    source = db.scalar(
        select(ReviewFile).where(
            ReviewFile.review_id == review.id, ReviewFile.file_path == finding.file_path
        )
    )
    event = db.scalar(
        select(ReviewPatchEvent)
        .where(
            ReviewPatchEvent.finding_id == finding.id,
            ReviewPatchEvent.event_type == "applied_to_upload",
        )
        .order_by(ReviewPatchEvent.created_at.desc())
    )
    if source is None or event is None:
        raise HTTPException(409, "There is no approved patch to roll back")
    try:
        patch_payload = json.loads(event.patch)
    except json.JSONDecodeError as exc:
        raise HTTPException(409, "Patch audit data is invalid") from exc
    if sha256(source.content) != patch_payload.get("applied_sha256"):
        raise HTTPException(409, "Uploaded source changed after patch application")
    original = patch_payload.get("original_content")
    if not isinstance(original, str):
        raise HTTPException(409, "Original uploaded source snapshot is unavailable")
    reverse_diff = "".join(
        difflib.unified_diff(
            source.content.splitlines(keepends=True),
            original.splitlines(keepends=True),
            fromfile=f"a/{source.file_path}",
            tofile=f"b/{source.file_path}",
        )
    )
    source.content = original
    source.sha256 = sha256(original)
    finding.status = "open"
    db.add(
        ReviewPatchEvent(
            finding_id=finding.id,
            user_id=user.id,
            event_type="rolled_back",
            patch=reverse_diff,
        )
    )
    db.commit()
    return PatchPreviewOutput(
        finding_id=finding.id,
        file_path=source.file_path,
        original_sha256=source.sha256,
        unified_diff=reverse_diff,
        explanation="Approved rollback restored the prior uploaded-source snapshot.",
        applied=False,
        rolled_back=True,
    )


@router.post("/{review_id}/feedback", status_code=201)
def add_feedback(
    review_id: UUID,
    payload: ReviewFeedbackInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = owned_review(review_id, user, db)
    feedback = ReviewFeedback(
        review_id=review.id,
        user_id=user.id,
        rating=payload.rating,
        comment=payload.comment.strip(),
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return {"id": feedback.id, "rating": feedback.rating, "created_at": feedback.created_at}
