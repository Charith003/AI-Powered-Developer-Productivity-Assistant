import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_alembic_upgrade_creates_ai_usage_code_review_and_test_schema(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    database = (tmp_path / "migrations.db").as_posix()
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+pysqlite:///{database}"
    env["JWT_SECRET"] = "migration-test-secret-longer-than-32-characters"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(tmp_path / "migrations.db") as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_usage)")}
        finding_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(review_findings)")
        }
        execution_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(test_executions)")
        }
        review_tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        active_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(test_executions)")
        }
    assert revision == "0007_raw_coverage_artifact"
    assert {
        "user_id",
        "project_id",
        "model",
        "input_tokens",
        "estimated_cost_usd",
        "status",
    } <= columns
    assert {"analyzer", "reasoning", "evidence", "suggested_patch"} <= finding_columns
    assert {
        "code_reviews",
        "review_files",
        "review_findings",
        "review_feedback",
        "review_patch_events",
    } <= review_tables
    assert {
        "test_generations",
        "test_executions",
        "test_case_results",
        "test_execution_events",
    } <= review_tables
    assert {
        "line_coverage",
        "branch_coverage",
        "uncovered_lines",
        "file_coverage",
        "failure_analysis",
    } <= execution_columns
    assert {"test_code_snapshot", "source_sha256", "test_sha256"} <= execution_columns
    assert "cancel_requested" in execution_columns
    assert "coverage_artifact" in execution_columns
    assert "uq_test_executions_active_generation" in active_indexes
