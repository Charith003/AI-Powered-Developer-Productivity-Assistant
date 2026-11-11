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
from app.db_urls import psycopg_connection_url
from app.models import TestExecution, TestGeneration, User

backend = Path(__file__).resolve().parents[1]


def main() -> None:
    # Generated identifiers are hex-only; credentials remain in-memory and are never logged.
    legacy_name = f"devpilot_legacy_{uuid4().hex}"
    admin_url = psycopg_connection_url(settings.database_url, database="postgres")
    legacy_sqlalchemy_url = make_url(settings.database_url).set(database=legacy_name)
    database_created = False
    engine = None
    try:
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(f'CREATE DATABASE "{legacy_name}"')
            database_created = True

        env = os.environ.copy()
        env["DATABASE_URL"] = legacy_sqlalchemy_url.render_as_string(hide_password=False)
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "0004_test_generation"],
            cwd=backend,
            env=env,
            check=True,
        )

        engine = create_engine(legacy_sqlalchemy_url)
        older_id, newer_id = str(uuid4()), str(uuid4())
        with Session(engine) as session:
            user = User(
                email=f"legacy-{uuid4()}@example.test",
                full_name="Legacy migration",
                password_hash="unused",
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
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=backend,
            env=env,
            check=True,
        )
        with Session(engine) as session:
            old = session.get(TestExecution, older_id)
            new = session.get(TestExecution, newer_id)
            assert old and old.execution_status == "infrastructure_failure"
            assert old.infrastructure_message == (
                "Closed duplicate active execution during reliability migration"
            )
            assert new and new.execution_status == "queued" and new.cancel_requested is False

            inspector = inspect(engine)
            indexes = {index["name"] for index in inspector.get_indexes("test_executions")}
            evidence = {
                "migration": "0004_to_head",
                "older_duplicate": old.execution_status,
                "newest_active": new.execution_status,
                "active_generation_index_present": (
                    "uq_test_executions_active_generation" in indexes
                ),
                "audit_table_present": inspector.has_table("test_execution_events"),
                "coverage_artifact_column_present": "coverage_artifact"
                in {column["name"] for column in inspector.get_columns("test_executions")},
            }
            assert evidence["active_generation_index_present"]
            assert evidence["audit_table_present"]
            assert evidence["coverage_artifact_column_present"]
            print(json.dumps(evidence))
    finally:
        if engine is not None:
            engine.dispose()
        if database_created:
            with psycopg.connect(admin_url, autocommit=True) as connection:
                connection.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (legacy_name,),
                )
                connection.execute(f'DROP DATABASE IF EXISTS "{legacy_name}"')


if __name__ == "__main__":
    main()
