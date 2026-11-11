"""Exercise a populated PostgreSQL 0004 database through current Alembic head."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
from sqlalchemy import MetaData, Table, create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import settings
from app.models import TestExecution, TestGeneration, User

backend = Path(__file__).resolve().parents[1]

legacy_name = f"devpilot_legacy_{uuid4().hex[:8]}"
admin_url = make_url(settings.database_url).set(database="postgres")
legacy_url = make_url(settings.database_url).set(database=legacy_name)

with psycopg.connect(
    admin_url.render_as_string(hide_password=False), autocommit=True
) as connection:
    connection.execute(f'CREATE DATABASE "{legacy_name}"')

env = os.environ.copy()
env["DATABASE_URL"] = legacy_url.render_as_string(hide_password=False)
subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "0004_test_generation"],
    cwd=backend,
    env=env,
    check=True,
)

engine = create_engine(legacy_url)
older_id, newer_id = str(uuid4()), str(uuid4())
with Session(engine) as session:
    user = User(
        email=f"legacy-{uuid4()}@example.test", full_name="Legacy migration", password_hash="unused"
    )
    session.add(user)
    session.flush()
    generation = TestGeneration(
        user_id=user.id,
        title="Legacy active execution",
        source_path="sample.py",
        source_content="def sample(): return 1",
        language="python",
        framework="pytest",
        generation_status="completed",
        test_plan=[],
        generated_test_content="def test_sample(): pass",
        validation_status="valid",
        validation_errors=[],
        ai_model=None,
        input_tokens=0,
        output_tokens=0,
    )
    session.add(generation)
    session.flush()
    executions = Table("test_executions", MetaData(), autoload_with=engine)
    now = datetime.now(UTC)
    common = {
        "generation_id": generation.id,
        "user_id": user.id,
        "test_code_snapshot": "def test_sample(): pass",
        "source_sha256": "a" * 64,
        "test_sha256": "b" * 64,
        "execution_status": "queued",
        "total_tests": 0,
        "passed_tests": 0,
        "failed_tests": 0,
        "skipped_tests": 0,
        "error_count": 0,
        "uncovered_lines": {},
        "file_coverage": {},
        "failure_analysis": [],
        "execution_duration": 0,
        "stdout": "",
        "stderr": "",
    }
    session.execute(
        executions.insert(),
        [
            {**common, "id": older_id, "created_at": datetime(2020, 1, 1, tzinfo=UTC)},
            {**common, "id": newer_id, "created_at": datetime(2021, 1, 1, tzinfo=UTC)},
        ],
    )
    session.commit()

subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend, env=env, check=True
)
with Session(engine) as session:
    old = session.get(TestExecution, older_id)
    new = session.get(TestExecution, newer_id)
    assert old and old.execution_status == "infrastructure_failure"
    assert (
        old.infrastructure_message
        == "Closed duplicate active execution during reliability migration"
    )
    assert new and new.execution_status == "queued" and new.cancel_requested is False
    evidence = {
        "migration": "0004_to_head",
        "older_duplicate": old.execution_status,
        "newest_active": new.execution_status,
        "audit_table_present": inspect(engine).has_table("test_execution_events"),
    }
    assert evidence["audit_table_present"]
    print(json.dumps(evidence))

engine.dispose()
with psycopg.connect(
    admin_url.render_as_string(hide_password=False), autocommit=True
) as connection:
    connection.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
        (legacy_name,),
    )
    connection.execute(f'DROP DATABASE "{legacy_name}"')
