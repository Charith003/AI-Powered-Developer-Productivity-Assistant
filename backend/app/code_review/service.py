import asyncio
from datetime import UTC, datetime
from time import monotonic

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.ai.exceptions import AIServiceError
from app.code_review.ai_review import AIReviewService
from app.code_review.analyzers.base import analyze
from app.code_review.normalizer import normalize_findings
from app.code_review.patch_generator import PatchGenerator
from app.code_review.schemas import CreateReviewRequest
from app.code_review.validators import sha256, validate_source
from app.config import Settings
from app.models import CodeReview, ReviewFile, ReviewFinding

AI_REVIEW_MAX_CHARS = 48_000


class CodeReviewService:
    """Orchestrates static and AI analysis; transport and persistence stay separate."""

    def __init__(self, db: Session, settings: Settings, ai_service_factory=None):
        self.db = db
        self.settings = settings
        self.ai_service_factory = ai_service_factory or AIReviewService

    async def analyze_code(self, *, user_id: str, payload: CreateReviewRequest) -> CodeReview:
        language, files = validate_source(payload)
        started = monotonic()
        review = CodeReview(
            user_id=user_id,
            project_id=str(payload.project_id) if payload.project_id else None,
            title=payload.title.strip() or "Code review",
            language=language,
            review_status="in_progress",
            source_type="uploaded",
            configuration={
                "requested_analyzers": payload.analyzers,
                "ai_enabled": payload.ai_enabled,
            },
            summary="Analysis is in progress.",
        )
        self.db.add(review)
        self.db.flush()
        for source in files:
            self.db.add(
                ReviewFile(
                    review_id=review.id,
                    file_path=source["path"],
                    content=source["content"],
                    sha256=sha256(source["content"]),
                )
            )
        self.db.commit()
        self.db.refresh(review)

        try:
            statuses, raw_findings = await run_in_threadpool(
                analyze, files, language, payload.analyzers, self.settings
            )
            if payload.ai_enabled:
                ai_service = self.ai_service_factory(self.db, self.settings)
                remaining = AI_REVIEW_MAX_CHARS
                ai_status = "completed"
                bounded_files = []
                for source in files:
                    if remaining <= 0:
                        ai_status = "partial_limit"
                        break
                    content = source["content"]
                    selected = content[:remaining]
                    remaining -= len(selected)
                    bounded_files.append({"path": source["path"], "content": selected})
                    if len(selected) < len(content):
                        ai_status = "partial_limit"
                        break
                try:
                    raw_findings.extend(
                        await ai_service.review_files(
                            user_id=user_id,
                            project_id=review.project_id,
                            files=bounded_files,
                        )
                    )
                except AIServiceError as exc:
                    ai_status = exc.code
                from app.code_review.schemas import AnalyzerStatus

                statuses.append(
                    AnalyzerStatus(
                        analyzer="ai_review",
                        status=ai_status,
                        message=(
                            "Source exceeded the 48,000-character AI review budget; later files were not sent."
                            if ai_status == "partial_limit"
                            else "AI review could not complete. Check provider configuration and usage history."
                            if ai_status != "completed"
                            else None
                        ),
                    )
                )
            findings = normalize_findings(raw_findings, files, language)
            for finding in findings:
                self.db.add(ReviewFinding(review_id=review.id, **finding))
            counts = {
                severity: 0 for severity in ("critical", "high", "medium", "low", "informational")
            }
            for finding in findings:
                counts[finding["severity"]] += 1
            review.total_findings = len(findings)
            review.critical_count = counts["critical"]
            review.high_count = counts["high"]
            review.medium_count = counts["medium"]
            review.low_count = counts["low"]
            review.informational_count = counts["informational"]
            review.execution_duration = max(0, int((monotonic() - started) * 1000))
            completed_analyzers = [status for status in statuses if status.status == "completed"]
            review.review_status = "completed" if completed_analyzers else "failed"
            unavailable = [status.analyzer for status in statuses if status.status != "completed"]
            origin_counts = {
                "static": sum(row["source"] == "static" for row in findings),
                "ai": sum(row["source"] == "ai" for row in findings),
            }
            review.summary = (
                f"{len(findings)} findings: {origin_counts['static']} from static analyzers and "
                f"{origin_counts['ai']} AI observations. "
                + (
                    f"Unavailable or incomplete analyzers: {', '.join(unavailable)}."
                    if unavailable
                    else "All configured analyzers completed."
                )
            )[:4000]
            review.configuration = {
                **review.configuration,
                "analyzers": [status.model_dump() for status in statuses],
                "ai_source_truncated": any(status.status == "partial_limit" for status in statuses),
            }
            review.completed_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(review)
            return review
        except asyncio.CancelledError:
            self._mark_failed(review.id, started)
            raise
        except Exception:
            self._mark_failed(review.id, started)
            raise

    def _mark_failed(self, review_id: str, started: float) -> None:
        self.db.rollback()
        review = self.db.get(CodeReview, review_id)
        if review is None:
            return
        review.review_status = "failed"
        review.execution_duration = max(0, int((monotonic() - started) * 1000))
        review.summary = "Analysis failed before completion. No passing result is available."
        review.completed_at = datetime.now(UTC)
        self.db.commit()

    def get_review(self, review_id: str, user_id: str) -> CodeReview | None:
        return self.db.scalar(
            select(CodeReview).where(CodeReview.id == review_id, CodeReview.user_id == user_id)
        )

    def list_findings(self, review_id: str, user_id: str, *, severity=None, category=None):
        review = self.get_review(review_id, user_id)
        if review is None:
            return None
        query = select(ReviewFinding).where(ReviewFinding.review_id == review.id)
        if severity:
            query = query.where(ReviewFinding.severity == severity)
        if category:
            query = query.where(ReviewFinding.category == category)
        return list(
            self.db.scalars(
                query.order_by(ReviewFinding.file_path, ReviewFinding.line_start).limit(500)
            )
        )

    async def generate_patch(self, *, user_id: str, review_id: str, finding_id: str):
        review = self.get_review(review_id, user_id)
        if review is None:
            raise LookupError("Review not found")
        finding = self.db.scalar(
            select(ReviewFinding).where(
                ReviewFinding.id == finding_id, ReviewFinding.review_id == review.id
            )
        )
        if finding is None:
            raise LookupError("Finding not found")
        source = self.db.scalar(
            select(ReviewFile).where(
                ReviewFile.review_id == review.id, ReviewFile.file_path == finding.file_path
            )
        )
        if source is None:
            raise ValueError("Review source snapshot is unavailable")
        if sha256(source.content) != source.sha256:
            raise ValueError("Source changed since the review; create a new review first")
        patch, updated, explanation = await PatchGenerator(self.db, self.settings).preview(
            user_id=user_id,
            project_id=review.project_id,
            path=source.file_path,
            content=source.content,
            title=finding.title,
            recommendation=finding.recommendation or finding.description,
        )
        return review, finding, source, patch, updated, explanation
