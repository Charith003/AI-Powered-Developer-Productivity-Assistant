import json

from app.ai.providers.base import ProviderResult
from app.config import settings
from app.test_generation.planner import plan_python
from app.test_generation.sandbox.results import parse_junit
from app.test_generation.sandbox.runner import DockerSandbox
from app.test_generation.sandbox.worker import execute_one, parse_coverage_from_text
from app.test_generation.schemas import GeneratedTestOutput, PlannedCase
from app.test_generation.validator import validate_python_test


def register(client, email):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Tests", "password": "A-strong-password-123"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_ast_planning_selects_categories_relevant_to_source():
    cases = plan_python(
        "def parse_count(value):\n    if not value.isdecimal():\n        raise ValueError()\n    return int(value)\n",
        ["normal", "boundary", "negative", "exception", "regression"],
    )
    selected = {case.category for case in cases}
    assert {"normal", "boundary", "negative", "exception"} <= selected
    assert "regression" not in selected
    assert all(case.target == "parse_count" for case in cases)


def test_ast_planning_rejects_invalid_source():
    import pytest

    with pytest.raises(ValueError, match="Source syntax"):
        plan_python("def broken(:", ["normal"])


def test_generated_pytest_validation_rejects_invalid_and_tautological_tests():
    assert validate_python_test("def test_missing(:", "sample.py")
    unsafe = "import sample\ndef test_add():\n    assert True\n"
    assert any("tautological" in error for error in validate_python_test(unsafe, "sample.py"))
    good = "import sample\ndef test_add():\n    assert sample.add(1, 2) == 3\n"
    assert validate_python_test(good, "sample.py") == []


def test_result_parser_uses_junit_and_actual_coverage_only():
    xml = """<testsuite tests="2" failures="1" skipped="0"><testcase classname="test_x" name="test_ok" time="0.1"/><testcase classname="test_x" name="test_bad" time="0.2"><failure message="expected 2">traceback</failure></testcase></testsuite>"""
    cases = parse_junit(xml)
    assert [case["status"] for case in cases] == ["passed", "failed"]
    coverage = parse_coverage_from_text(
        json.dumps(
            {
                "totals": {"percent_covered": 75.0, "num_branches": 4, "covered_branches": 2},
                "files": {"/workspace/math_ops.py": {"missing_lines": [3, 8]}},
            }
        )
    )
    assert coverage == {
        "line_coverage": 75.0,
        "branch_coverage": 50.0,
        "uncovered_lines": {"math_ops.py": [3, 8]},
        "file_coverage": {
            "math_ops.py": {
                "statements": 0,
                "covered_statements": 0,
                "line_percent": None,
                "branch_percent": None,
            }
        },
    }
    assert coverage["file_coverage"] == {
        "math_ops.py": {
            "statements": 0,
            "covered_statements": 0,
            "line_percent": None,
            "branch_percent": None,
        }
    }
    assert parse_coverage_from_text("not coverage") == {
        "line_coverage": None,
        "branch_coverage": None,
        "uncovered_lines": {},
        "file_coverage": {},
    }


def test_docker_sandbox_command_has_required_isolation_flags(tmp_path):
    from app.config import Settings

    digest_image = "registry.example/test:1@sha256:" + "a" * 64
    runner = DockerSandbox(Settings(test_sandbox_image=digest_image), docker_path="docker")
    argv = runner.command(tmp_path, "devpilot-tests-123", "src/math_ops.py", "math_ops", False)
    assert runner.ready
    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert "--read-only" in argv and "--cap-drop=ALL" in argv
    assert (
        argv[argv.index("--user") + 1] == "0:0"
    )  # trusted bootstrap drops privileges before pytest
    assert argv[argv.index("--pid") + 1] == "private"
    assert argv[argv.index("--ipc") + 1] == "private"
    assert "seccomp=unconfined" not in argv
    assert {"--cap-add=SETUID", "--cap-add=SETGID", "--cap-add=KILL"} <= set(argv)
    assert "--pids-limit" in argv and "--memory" in argv and "--cpus" in argv
    assert "--memory-swap" in argv and "--ulimit" in argv
    assert any("nr_inodes=4096" in arg for arg in argv)
    assert "--pull=never" in argv
    assert any("/inputs,readonly" in arg for arg in argv)
    assert "--privileged" not in argv and "-v" not in argv and "--volume" not in argv
    assert argv[argv.index("python", argv.index(digest_image) + 1) :] == [
        "python",
        "/opt/devpilot/runner.py",
        "--source",
        "src/math_ops.py",
        "--module",
        "math_ops",
    ]


def test_sandbox_digest_verification_matches_repo_digest(monkeypatch):
    import subprocess

    from app.config import Settings

    digest = "a" * 64
    image = f"registry.example/devpilot/test:ci@sha256:{digest}"
    runner = DockerSandbox(Settings(test_sandbox_image=image), docker_path="docker")
    monkeypatch.setattr(
        "app.test_generation.sandbox.runner.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout=json.dumps([f"registry.example/devpilot/test@sha256:{digest}"]),
            stderr="",
        ),
    )
    assert runner.verify_image_digest()
    monkeypatch.setattr(
        "app.test_generation.sandbox.runner.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="[]", stderr=""),
    )
    assert not runner.verify_image_digest()


def test_worker_records_missing_sandbox_as_infrastructure_failure(client, monkeypatch):

    headers = register(client, "sandbox-missing@example.com")
    generation_response = client.post(
        "/api/v1/tests/generate",
        headers=headers,
        json={
            "source_path": "sample.py",
            "source_content": "def add(a, b): return a + b",
            "framework": "pytest",
        },
    )
    assert generation_response.status_code == 503
    assert generation_response.json()["error"]["code"] == "ai_not_configured"


class MockTestProvider:
    async def generate_structured(self, *, prompt, instructions, response_schema):
        assert '"source_code_untrusted"' in prompt
        assert "solely as untrusted data" in instructions
        return ProviderResult(
            GeneratedTestOutput(
                title="Addition tests",
                plan=[PlannedCase(target="add", objective="Check addition", category="normal")],
                test_code="import sample\n\ndef test_add():\n    assert sample.add(2, 3) == 5\n",
            ),
            "openai",
            "mock-model",
            100,
            40,
            140,
        )

    async def close(self):
        return None


def test_generation_validation_edit_queue_and_owner_isolation(client, monkeypatch):
    from app.test_generation import service

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(service, "create_provider", lambda _: MockTestProvider())
    owner = register(client, "test-generator-owner@example.com")
    created = client.post(
        "/api/v1/tests/generate",
        headers=owner,
        json={
            "title": "Addition",
            "source_path": "sample.py",
            "source_content": "def add(a, b): return a + b",
        },
    )
    assert created.status_code == 201, created.text
    generation = created.json()
    assert generation["validation_status"] == "valid"
    assert generation["test_plan"][0]["target"] == "add"
    assert (
        client.post(f"/api/v1/tests/{generation['id']}/validate", headers=owner).json()[
            "validation_status"
        ]
        == "valid"
    )
    edited = client.patch(
        f"/api/v1/tests/{generation['id']}",
        headers=owner,
        json={"test_code": "import sample\ndef test_add():\n    assert sample.add(0, 0) == 0\n"},
    )
    assert edited.status_code == 200 and edited.json()["validation_status"] == "valid"
    queued = client.post(f"/api/v1/tests/{generation['id']}/execute", headers=owner)
    assert queued.status_code == 202 and queued.json()["execution_status"] == "queued"
    assert queued.json()["test_sha256"]
    duplicate = client.post(f"/api/v1/tests/{generation['id']}/execute", headers=owner)
    assert duplicate.status_code == 202 and duplicate.json()["id"] == queued.json()["id"]
    events = client.get(f"/api/v1/tests/executions/{queued.json()['id']}/events", headers=owner)
    assert events.status_code == 200 and events.json()[0]["event_type"] == "execution_queued"
    assert (
        client.get(f"/api/v1/tests/executions/{queued.json()['id']}", headers=owner).json()[
            "execution_status"
        ]
        == "queued"
    )
    assert any(
        row["feature"] == "test_generation"
        for row in client.get("/api/v1/ai/usage", headers=owner).json()
    )
    metrics = client.get("/api/v1/tests/summary", headers=owner).json()
    assert metrics["total_generations"] == 1 and metrics["total_executions"] == 1
    assert metrics["passed_tests"] == metrics["failed_tests"] == 0
    assert metrics["average_line_coverage"] is None
    outsider = register(client, "test-generator-outsider@example.com")
    assert client.get(f"/api/v1/tests/{generation['id']}", headers=outsider).status_code == 404
    assert (
        client.get(f"/api/v1/tests/executions/{queued.json()['id']}", headers=outsider).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/tests/executions/{queued.json()['id']}/events", headers=outsider
        ).status_code
        == 404
    )
    from app.database import get_db
    from app.models import TestExecution

    db = next(client.app.dependency_overrides[get_db]())
    try:
        row = db.get(TestExecution, queued.json()["id"])
        row.execution_status = "running"
        db.commit()
    finally:
        db.close()
    running_cancel = client.post(
        f"/api/v1/tests/executions/{queued.json()['id']}/cancel", headers=owner
    )
    assert running_cancel.status_code == 200 and running_cancel.json()["cancel_requested"] is True
    db = next(client.app.dependency_overrides[get_db]())
    try:
        row = db.get(TestExecution, queued.json()["id"])
        row.execution_status = "queued"
        row.cancel_requested = False
        db.commit()
    finally:
        db.close()
    cancelled = client.post(f"/api/v1/tests/executions/{queued.json()['id']}/cancel", headers=owner)
    assert cancelled.status_code == 200 and cancelled.json()["execution_status"] == "cancelled"
    assert (
        client.post(f"/api/v1/tests/executions/{queued.json()['id']}/cancel", headers=owner).json()[
            "execution_status"
        ]
        == "cancelled"
    )
    event_types = [
        event["event_type"]
        for event in client.get(
            f"/api/v1/tests/executions/{queued.json()['id']}/events", headers=owner
        ).json()
    ]
    assert "queued_execution_cancelled" in event_types
    from datetime import UTC, datetime, timedelta

    from app.test_generation.sandbox.worker import recover_stale_jobs

    db = next(client.app.dependency_overrides[get_db]())
    try:
        row = db.get(TestExecution, queued.json()["id"])
        row.execution_status = "running"
        row.started_at = datetime.now(UTC) - timedelta(minutes=10)
        db.commit()
        assert (
            recover_stale_jobs(
                db, DockerSandbox(settings, docker_path=None), stale_after_seconds=60
            )
            == 1
        )
        db.refresh(row)
        assert row.execution_status == "infrastructure_failure"
        assert "Worker disappeared" in row.infrastructure_message
    finally:
        db.close()


def test_worker_does_not_claim_success_when_docker_is_unavailable(client, monkeypatch):
    from app.database import get_db

    headers = register(client, "execution-availability@example.com")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    from app.test_generation import service

    monkeypatch.setattr(service, "create_provider", lambda _: MockTestProvider())
    response = client.post(
        "/api/v1/tests/generate",
        headers=headers,
        json={"source_path": "sample.py", "source_content": "def add(a, b): return a + b"},
    )
    generation_id = response.json()["id"]
    execution = client.post(f"/api/v1/tests/{generation_id}/execute", headers=headers).json()
    db = next(client.app.dependency_overrides[get_db]())
    try:
        result = execute_one(db, DockerSandbox(settings, docker_path=None))
        assert result is not None and result.execution_status == "infrastructure_failure"
        assert result.total_tests == result.passed_tests == 0
    finally:
        db.close()
    polled = client.get(f"/api/v1/tests/executions/{execution['id']}", headers=headers).json()
    assert polled["execution_status"] == "infrastructure_failure"
    assert "not executed" in polled["infrastructure_message"]
