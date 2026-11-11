"""PostgreSQL plus Docker integration checks; mandatory in sandbox-verification CI."""

import hashlib
import json
import os
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import (
    TestCaseResult as CaseRecord,
)
from app.models import (
    TestExecution as ExecutionRecord,
)
from app.models import TestExecutionEvent as ExecutionEventRecord
from app.models import (
    TestGeneration as GenerationRecord,
)
from app.models import (
    User,
)
from app.test_generation.sandbox.runner import DockerSandbox
from app.test_generation.sandbox.worker import execute_one, recover_stale_jobs
from app.security import create_access_token

pytestmark = pytest.mark.skipif(
    os.getenv("DEVPILOT_POSTGRES_INTEGRATION") != "1",
    reason="Requires the PostgreSQL and Docker integration workflow",
)


def create_job(
    session,
    *,
    test_code,
    queue=True,
    source="def choose(value):\n    if value > 0:\n        return 'up'\n    return 'down'\n",
):
    user = User(
        email=f"sandbox-{uuid.uuid4()}@example.test",
        full_name="Sandbox CI",
        password_hash="not-used",
    )
    session.add(user)
    session.flush()
    generation = GenerationRecord(
        user_id=user.id,
        title="Sandbox CI fixture",
        source_path="math_ops.py",
        source_content=source,
        language="python",
        framework="pytest",
        generation_status="completed",
        test_plan=[],
        generated_test_content=test_code,
        validation_status="valid",
        validation_errors=[],
        ai_model=None,
        input_tokens=0,
        output_tokens=0,
    )
    session.add(generation)
    session.flush()
    execution = None
    if queue:
        execution = ExecutionRecord(
            generation_id=generation.id,
            user_id=user.id,
            test_code_snapshot=test_code,
            source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            test_sha256=hashlib.sha256(test_code.encode()).hexdigest(),
            execution_status="queued",
        )
        session.add(execution)
        session.flush()
    return user.id, generation.id, execution.id if execution else None


def cleanup(session, user_ids):
    executions = list(
        session.scalars(select(ExecutionRecord).where(ExecutionRecord.user_id.in_(user_ids)))
    )
    execution_ids = [row.id for row in executions]
    if execution_ids:
        session.query(CaseRecord).filter(CaseRecord.execution_id.in_(execution_ids)).delete(
            synchronize_session=False
        )
        session.query(ExecutionRecord).filter(ExecutionRecord.id.in_(execution_ids)).delete(
            synchronize_session=False
        )
    session.query(GenerationRecord).filter(GenerationRecord.user_id.in_(user_ids)).delete(
        synchronize_session=False
    )
    session.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    session.commit()


def test_postgres_worker_persists_real_results_and_coverage():
    db = SessionLocal()
    user_ids = []
    try:
        user_id, generation_id, execution_id = create_job(
            db,
            queue=False,
            test_code="""import math_ops
def test_positive(): assert math_ops.choose(2) == "up"
def test_zero(): assert math_ops.choose(0) == "down"
""",
        )
        user_ids.append(user_id)
        db.commit()

        outsider = User(
            email=f"sandbox-outsider-{uuid.uuid4()}@example.test",
            full_name="Not the generation owner",
            password_hash="not-used",
        )
        db.add(outsider)
        db.commit()
        user_ids.append(outsider.id)

        with TestClient(app) as client:
            owner_token, _ = create_access_token(user_id)
            outsider_token, _ = create_access_token(outsider.id)
            endpoint = f"/api/v1/tests/{generation_id}/execute"
            forbidden = client.post(
                endpoint, headers={"Authorization": f"Bearer {outsider_token}"}
            )
            assert forbidden.status_code == 404

            submitted = client.post(
                endpoint, headers={"Authorization": f"Bearer {owner_token}"}
            )
            assert submitted.status_code == 202, submitted.text
            execution_id = submitted.json()["id"]
            assert submitted.json()["execution_status"] == "queued"

            repeated = client.post(
                endpoint, headers={"Authorization": f"Bearer {owner_token}"}
            )
            assert repeated.status_code == 202, repeated.text
            assert repeated.json()["id"] == execution_id

        queued_event = db.scalar(
            select(ExecutionEventRecord).where(
                ExecutionEventRecord.execution_id == execution_id,
                ExecutionEventRecord.event_type == "execution_queued",
            )
        )
        assert queued_event is not None

        savepoint = db.begin_nested()
        try:
            db.add(
                ExecutionRecord(
                    generation_id=generation_id,
                    user_id=user_id,
                    test_code_snapshot="def test_duplicate(): pass",
                    source_sha256="0" * 64,
                    test_sha256="1" * 64,
                    execution_status="queued",
                )
            )
            with pytest.raises(IntegrityError):
                db.flush()
        finally:
            savepoint.rollback()
        execution = execute_one(db, DockerSandbox(settings))
        assert execution.id == execution_id
        assert execution and execution.execution_status == "completed"
        assert (execution.total_tests, execution.passed_tests, execution.failed_tests) == (2, 2, 0)
        assert execution.line_coverage is not None and execution.branch_coverage is not None
        assert execution.coverage_artifact
        assert (
            round(json.loads(execution.coverage_artifact)["totals"]["percent_covered"], 2)
            == execution.line_coverage
        )
        cases = list(db.scalars(select(CaseRecord).where(CaseRecord.execution_id == execution.id)))
        assert len(cases) == 2 and all(case.status == "passed" for case in cases)
        assert execution.completed_at is not None and execution.exit_code == 0
    finally:
        cleanup(db, user_ids) if user_ids else None
        db.close()


def test_postgres_unique_active_index_and_competing_workers():
    db = SessionLocal()
    user_ids = []
    try:
        for _ in range(2):
            user_id, _, _ = create_job(
                db,
                test_code="""import math_ops
def test_basic(): assert math_ops.choose(1) == "up"
""",
            )
            user_ids.append(user_id)
        db.commit()
        execution_ids = list(
            db.scalars(select(ExecutionRecord.id).where(ExecutionRecord.user_id.in_(user_ids)))
        )

        def claim_once():
            with SessionLocal() as worker_db:
                claimed = execute_one(worker_db, DockerSandbox(settings))
                return (
                    claimed.id if claimed else None,
                    claimed.execution_status if claimed else None,
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: claim_once(), range(2)))
        assert {row[0] for row in results} == set(execution_ids)
        assert all(row[1] == "completed" for row in results)
    finally:
        cleanup(db, user_ids) if user_ids else None
        db.close()


def test_postgres_cancellation_request_stops_live_container():
    db = SessionLocal()
    user_ids = []
    try:
        user_id, _, execution_id = create_job(
            db,
            test_code="""import time
def test_wait_for_cancel():
    time.sleep(25)
""",
        )
        user_ids.append(user_id)
        db.commit()

        def execute():
            with SessionLocal() as worker_db:
                result = execute_one(worker_db, DockerSandbox(settings))
                return result.execution_status if result else None

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(execute)
            deadline = time.monotonic() + 20
            container_name = f"devpilot-tests-{execution_id.replace('-', '')}"
            while time.monotonic() < deadline:
                db.expire_all()
                row = db.get(ExecutionRecord, execution_id)
                if row and row.execution_status == "running" and time.monotonic() > deadline - 15:
                    break
                time.sleep(0.15)
            row = db.get(ExecutionRecord, execution_id)
            assert row and row.execution_status == "running"
            time.sleep(2)
            row.cancel_requested = True
            db.commit()
            assert future.result(timeout=15) == "cancelled"
            check = subprocess.run(
                ["docker", "inspect", container_name], capture_output=True, check=False
            )
            assert check.returncode != 0, "cancelled execution container still exists"
    finally:
        cleanup(db, user_ids) if user_ids else None
        db.close()


def test_postgres_stale_recovery_removes_orphan_container():
    db = SessionLocal()
    user_ids = []
    container_name = None
    try:
        user_id, _, execution_id = create_job(db, test_code="def test_placeholder(): pass\n")
        user_ids.append(user_id)
        row = db.get(ExecutionRecord, execution_id)
        row.execution_status = "running"
        row.started_at = datetime.now(UTC) - timedelta(minutes=10)
        db.commit()
        container_name = f"devpilot-tests-{execution_id.replace('-', '')}"
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                container_name,
                "--network",
                "none",
                "--label",
                f"devpilot.execution-id={execution_id.replace('-', '').lower()}",
                "--read-only",
                "--memory",
                "128m",
                "--pids-limit",
                "32",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                settings.test_sandbox_image or "",
                "python",
                "-c",
                "import time; time.sleep(120)",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert recover_stale_jobs(db, DockerSandbox(settings), stale_after_seconds=60) == 1
        db.refresh(row)
        assert row.execution_status == "infrastructure_failure"
        assert "Worker disappeared" in row.infrastructure_message
        check = subprocess.run(
            ["docker", "inspect", container_name], capture_output=True, check=False
        )
        assert check.returncode != 0, "stale recovery left an orphan container"
    finally:
        if container_name:
            subprocess.run(
                ["docker", "rm", "--force", container_name], capture_output=True, check=False
            )
        cleanup(db, user_ids) if user_ids else None
        db.close()
