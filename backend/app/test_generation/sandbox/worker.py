import hashlib
import json
import logging
import os
import re
import socket
from datetime import UTC, datetime, timedelta
from xml.etree.ElementTree import ParseError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import TestCaseResult, TestExecution, TestExecutionEvent, TestGeneration
from app.test_generation.sandbox.results import parse_junit
from app.test_generation.sandbox.runner import DockerSandbox

logger = logging.getLogger(__name__)


def record_event(db: Session, execution_id: str, event_type: str, **details) -> None:
    db.add(TestExecutionEvent(execution_id=execution_id, event_type=event_type, details=details))
    logger.info(
        json.dumps(
            {
                "event": "test_execution_lifecycle",
                "execution_id": execution_id,
                "event_type": event_type,
                **details,
            },
            sort_keys=True,
        )
    )


def recover_stale_jobs(
    db: Session,
    sandbox: DockerSandbox,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = 150,
) -> int:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(seconds=stale_after_seconds)
    stale = list(
        db.scalars(
            select(TestExecution)
            .where(
                TestExecution.execution_status == "running",
                TestExecution.started_at.is_not(None),
                TestExecution.started_at < cutoff,
            )
            .with_for_update(skip_locked=True)
        )
    )
    for row in stale:
        removed = sandbox.remove_execution(row.id)
        if row.cancel_requested and removed:
            row.execution_status = "cancelled"
            row.infrastructure_message = "Cancelled after the worker stopped responding"
        else:
            row.execution_status = "infrastructure_failure"
            row.infrastructure_message = (
                "Worker disappeared and orphan container cleanup could not be confirmed"
                if not removed
                else "Worker disappeared before reporting execution results"
            )
        row.completed_at = now
        row.cancel_requested = False
        record_event(db, row.id, "stale_job_recovered", cleanup_confirmed=removed)
    if stale:
        db.commit()
    return len(stale)


def execute_one(db: Session, sandbox: DockerSandbox) -> TestExecution | None:
    recover_stale_jobs(
        db, sandbox, stale_after_seconds=max(150, settings.test_sandbox_timeout_seconds + 30)
    )
    execution = db.scalar(
        select(TestExecution)
        .where(TestExecution.execution_status == "queued")
        .order_by(TestExecution.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if execution is None:
        return None
    generation = db.get(TestGeneration, execution.generation_id)
    if generation is None:
        execution.execution_status = "infrastructure_failure"
        execution.infrastructure_message = "Test generation record no longer exists"
        execution.completed_at = datetime.now(UTC)
        record_event(
            db, execution.id, "execution_finalized", execution_status=execution.execution_status
        )
        db.commit()
        return execution
    source_hash = hashlib.sha256(generation.source_content.encode("utf-8")).hexdigest()
    test_hash = hashlib.sha256(execution.test_code_snapshot.encode("utf-8")).hexdigest()
    if source_hash != execution.source_sha256 or test_hash != execution.test_sha256:
        execution.execution_status = "error"
        execution.infrastructure_message = (
            "Execution snapshot hash validation failed; source was not run"
        )
        execution.completed_at = datetime.now(UTC)
        record_event(
            db, execution.id, "execution_finalized", execution_status=execution.execution_status
        )
        db.commit()
        return execution
    execution.execution_status = "running"
    execution.started_at = datetime.now(UTC)
    record_event(
        db, execution.id, "worker_claimed", worker_id=f"{socket.gethostname()}:{os.getpid()}"
    )
    db.commit()
    execution_id = execution.id

    def cancellation_requested() -> bool:
        with SessionLocal() as cancellation_db:
            current = cancellation_db.get(TestExecution, execution_id)
            return bool(current and current.cancel_requested)

    collection = sandbox.run(
        source_path=generation.source_path,
        source=generation.source_content,
        test_code=execution.test_code_snapshot,
        collect_only=True,
        run_id=execution_id,
        cancel_check=cancellation_requested,
    )
    record_event(
        db,
        execution.id,
        "container_finished",
        phase="collection",
        container_id=collection.container_id,
        image_digest=(sandbox.settings.test_sandbox_image or "").rsplit("@", 1)[-1],
        execution_status=collection.status,
        cleanup_confirmed=collection.cleanup_confirmed,
    )
    if collection.status != "completed":
        execution.execution_status = collection.status
        execution.cancel_requested = False
        execution.infrastructure_message = collection.message
        execution.exit_code = collection.exit_code
        execution.stdout = collection.stdout[:32_000]
        execution.stderr = collection.stderr[:32_000]
        execution.completed_at = datetime.now(UTC)
        record_event(
            db, execution.id, "execution_finalized", execution_status=execution.execution_status
        )
        db.commit()
        return execution
    collected = len(re.findall(r"::test_[A-Za-z0-9_]+", collection.stdout))
    if collected > 100:
        execution.execution_status = "error"
        execution.cancel_requested = False
        execution.infrastructure_message = (
            "Pytest discovery exceeded the 100-test job limit; test body was not executed"
        )
        execution.exit_code = collection.exit_code
        execution.completed_at = datetime.now(UTC)
        record_event(
            db, execution.id, "execution_finalized", execution_status=execution.execution_status
        )
        db.commit()
        return execution
    if collection.exit_code != 0 or collected == 0:
        execution.execution_status = "error"
        execution.cancel_requested = False
        execution.infrastructure_message = (
            "Pytest collection failed or discovered no tests; test body was not executed"
        )
        execution.exit_code = collection.exit_code
        execution.stdout = collection.stdout[:32_000]
        execution.stderr = collection.stderr[:32_000]
        execution.completed_at = datetime.now(UTC)
        record_event(
            db, execution.id, "execution_finalized", execution_status=execution.execution_status
        )
        db.commit()
        return execution

    result = sandbox.run(
        source_path=generation.source_path,
        source=generation.source_content,
        test_code=execution.test_code_snapshot,
        run_id=execution_id,
        cancel_check=cancellation_requested,
    )
    record_event(
        db,
        execution.id,
        "container_finished",
        phase="execution",
        container_id=result.container_id,
        image_digest=(sandbox.settings.test_sandbox_image or "").rsplit("@", 1)[-1],
        execution_status=result.status,
        exit_code=result.exit_code,
        duration_ms=result.duration_ms,
        cleanup_confirmed=result.cleanup_confirmed,
    )
    execution.exit_code = result.exit_code
    execution.stdout = result.stdout[:32_000]
    execution.stderr = result.stderr[:32_000]
    execution.execution_duration = result.duration_ms
    execution.coverage_artifact = result.coverage_json[: settings.test_sandbox_output_bytes] or None
    if result.status != "completed":
        execution.execution_status = result.status
        execution.infrastructure_message = result.message
    else:
        try:
            cases = parse_junit(result.junit_xml)
        except (ParseError, ValueError, TypeError):
            cases = []
        if not cases:
            execution.execution_status = "error"
            execution.infrastructure_message = "Test runner produced no parseable test case results"
        else:
            for case in cases:
                db.add(TestCaseResult(execution_id=execution.id, **case))
            execution.total_tests = len(cases)
            execution.passed_tests = sum(row["status"] == "passed" for row in cases)
            execution.failed_tests = sum(row["status"] == "failed" for row in cases)
            execution.skipped_tests = sum(row["status"] == "skipped" for row in cases)
            execution.error_count = sum(row["status"] == "error" for row in cases)
            execution.execution_status = (
                "failed"
                if execution.failed_tests
                else "error"
                if execution.error_count
                else "completed"
            )
            coverage = parse_coverage_from_text(result.coverage_json)
            execution.line_coverage = coverage["line_coverage"]
            execution.branch_coverage = coverage["branch_coverage"]
            execution.uncovered_lines = coverage["uncovered_lines"]
            execution.file_coverage = coverage["file_coverage"]
    execution.completed_at = datetime.now(UTC)
    execution.cancel_requested = False
    record_event(
        db,
        execution.id,
        "execution_finalized",
        execution_status=execution.execution_status,
        total_tests=execution.total_tests,
        passed_tests=execution.passed_tests,
        failed_tests=execution.failed_tests,
        skipped_tests=execution.skipped_tests,
        error_count=execution.error_count,
        line_coverage=execution.line_coverage,
        branch_coverage=execution.branch_coverage,
    )
    db.commit()
    db.refresh(execution)
    return execution


def parse_coverage_from_text(text: str) -> dict:
    import json

    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        return {
            "line_coverage": None,
            "branch_coverage": None,
            "uncovered_lines": {},
            "file_coverage": {},
        }
    files = raw.get("files", {})
    totals = raw.get("totals", {})
    branches = totals.get("num_branches", 0)
    file_coverage = {}
    for name, data in files.items():
        summary = data.get("summary", {})
        file_branches = summary.get("num_branches", 0)
        file_coverage[name.removeprefix("/workspace/")] = {
            "statements": summary.get("num_statements", 0),
            "covered_statements": summary.get("covered_lines", 0),
            "line_percent": round(float(summary["percent_covered"]), 2)
            if summary.get("percent_covered") is not None
            else None,
            "branch_percent": round(summary.get("covered_branches", 0) / file_branches * 100, 2)
            if file_branches
            else None,
        }
    return {
        "line_coverage": round(float(totals["percent_covered"]), 2)
        if totals.get("percent_covered") is not None
        else None,
        "branch_coverage": round(totals.get("covered_branches", 0) / branches * 100, 2)
        if branches
        else None,
        "uncovered_lines": {
            name.removeprefix("/workspace/"): data.get("missing_lines", [])
            for name, data in files.items()
            if data.get("missing_lines")
        },
        "file_coverage": file_coverage,
    }
