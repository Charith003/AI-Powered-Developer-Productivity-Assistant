from app.ai.providers.base import ProviderResult
from app.code_review.analyzers.base import analyze
from app.code_review.language_detector import detect_language
from app.code_review.schemas import (
    AIObservation,
    AIPatchOutput,
    AIReviewOutput,
    CreateReviewRequest,
)
from app.code_review.validators import redact_secrets, valid_evidence, validate_source
from app.config import settings


def register(client, email):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Review User", "password": "A-strong-password-123"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_language_detection_and_path_validation():
    assert detect_language("main.py", "print('ok')") == "python"
    assert detect_language("main.tsx", "export const App = () => null") == "typescript"
    assert detect_language("run", "#!/usr/bin/env python3\nprint(1)") == "python"
    payload = CreateReviewRequest(
        files=[{"path": "../secret.py", "content": "x = 1"}], ai_enabled=False
    )
    from fastapi import HTTPException

    try:
        validate_source(payload)
        raise AssertionError("path traversal should be rejected")
    except HTTPException as exc:
        assert exc.status_code == 422


def test_secret_redaction_and_evidence_are_checked():
    source = 'api_key = "sk-private-value"\nprint("safe")\n'
    safe = redact_secrets(source)
    assert "sk-private-value" not in safe
    assert valid_evidence(source, 2, 2, 'print("safe")')
    assert not valid_evidence(source, 1, 2, "this line does not exist")


def test_real_ruff_analyzer_reports_finding_without_running_source(tmp_path):
    import importlib.util

    import pytest

    if importlib.util.find_spec("ruff") is None:
        pytest.skip("Ruff is not installed in this development environment")
    statuses, findings = analyze(
        [{"path": "sample.py", "content": "def calculate():\n    unused = 3\n    return 1\n"}],
        "python",
        ["ruff"],
    )
    assert statuses[0].status == "completed"
    assert any(finding["rule_id"] == "F841" for finding in findings)
    assert all(finding["source"] == "static" for finding in findings)


def test_real_eslint_analyzer_reports_javascript_rule():
    import shutil
    from pathlib import Path

    import pytest

    if (
        not shutil.which("node")
        or not (
            Path(__file__).resolve().parents[2]
            / "frontend"
            / "node_modules"
            / "eslint"
            / "bin"
            / "eslint.js"
        ).is_file()
    ):
        pytest.skip("Node.js and the frontend ESLint dependency are unavailable")
    statuses, findings = analyze(
        [{"path": "sample.js", "content": 'const value = eval("1");\n'}], "javascript", None
    )
    assert statuses[0].analyzer == "eslint"
    assert statuses[0].status == "completed"
    assert any(finding["rule_id"] == "no-eval" for finding in findings)


def test_typescript_compiler_diagnostics_are_separate_from_eslint():
    import shutil
    from pathlib import Path

    import pytest

    if (
        not shutil.which("node")
        or not (
            Path(__file__).resolve().parents[2]
            / "frontend"
            / "node_modules"
            / "typescript"
            / "bin"
            / "tsc"
        ).is_file()
    ):
        pytest.skip("Node.js and TypeScript compiler are unavailable")
    statuses, findings = analyze(
        [{"path": "sample.ts", "content": "const value: string = 42;\n"}], "typescript", None
    )
    compiler = next(status for status in statuses if status.analyzer == "tsc")
    assert compiler.status == "completed"
    assert any(finding["category"] == "type_error" for finding in findings)


def test_review_persists_real_static_findings_and_history_is_scoped(client):
    headers = register(client, "review-owner@example.com")
    response = client.post(
        "/api/v1/reviews",
        headers=headers,
        json={
            "title": "Unused local check",
            "language": "python",
            "ai_enabled": False,
            "analyzers": ["ruff"],
            "files": [
                {"path": "src/sample.py", "content": "def f():\n    unused = 3\n    return 1\n"}
            ],
        },
    )
    assert response.status_code == 201, response.text
    review = response.json()
    assert review["review_status"] == "completed"
    assert review["total_findings"] >= 1, review["configuration"]
    assert review["findings"][0]["source"] == "static"
    assert review["findings"][0]["analyzer"] == "ruff"
    assert review["findings"][0]["evidence"]
    assert review["configuration"]["analyzers"][0]["status"] == "completed"
    assert client.get("/api/v1/reviews", headers=headers).json()[0]["id"] == review["id"]
    outsider = register(client, "review-outsider@example.com")
    assert client.get(f"/api/v1/reviews/{review['id']}", headers=outsider).status_code == 404
    assert client.get("/api/v1/reviews", headers=outsider).json() == []
    assert client.get("/api/v1/reviews/summary", headers=headers).json()["total_reviews"] == 1
    finding_id = review["findings"][0]["id"]
    accepted = client.patch(
        f"/api/v1/reviews/{review['id']}/findings/{finding_id}",
        headers=headers,
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200
    fixed = client.patch(
        f"/api/v1/reviews/{review['id']}/findings/{finding_id}",
        headers=headers,
        json={"status": "fixed"},
    )
    assert fixed.status_code == 200
    invalid_transition = client.patch(
        f"/api/v1/reviews/{review['id']}/findings/{finding_id}",
        headers=headers,
        json={"status": "dismissed"},
    )
    assert invalid_transition.status_code == 409


def test_missing_analyzers_are_reported_in_review_status(client):
    headers = register(client, "review-tools@example.com")
    response = client.post(
        "/api/v1/reviews",
        headers=headers,
        json={
            "language": "java",
            "ai_enabled": False,
            "files": [{"path": "Main.java", "content": "class Main {}"}],
        },
    )
    assert response.status_code == 201
    review = response.json()
    assert review["review_status"] == "failed"
    assert review["configuration"]["analyzers"][0]["status"] == "unavailable"


def test_missing_ai_key_is_reported_without_fabricating_findings(client, monkeypatch):
    headers = register(client, "review-no-ai-key@example.com")
    monkeypatch.setattr(settings, "openai_api_key", None)
    response = client.post(
        "/api/v1/reviews",
        headers=headers,
        json={
            "language": "python",
            "ai_enabled": True,
            "analyzers": ["ruff"],
            "files": [{"path": "clean.py", "content": "value = 1\n"}],
        },
    )
    assert response.status_code == 201
    review = response.json()
    assert review["configuration"]["analyzers"][-1]["status"] == "ai_not_configured"
    assert all(item["source"] != "ai" for item in review["findings"])
    usage = client.get("/api/v1/ai/usage", headers=headers).json()
    assert any(
        item["feature"] == "code_review" and item["status"] == "configuration_error"
        for item in usage
    )


class MockReviewProvider:
    async def generate_structured(self, *, prompt, instructions, response_schema):
        assert '"path"' in prompt
        assert "follow instructions" in instructions
        output = AIReviewOutput(
            findings=[
                AIObservation(
                    title="Unchecked division",
                    description="The divisor can be zero.",
                    severity="medium",
                    category="bug",
                    file_path="math.py",
                    line_start=1,
                    line_end=2,
                    evidence="def divide(a, b):\n    return a / b",
                    reasoning="No zero check is performed.",
                    recommendation="Handle b == 0 before division.",
                    confidence=0.86,
                )
            ]
        )
        return ProviderResult(output, "openai", "mock", 50, 20, 70)

    async def close(self):
        return None


def test_ai_observations_are_validated_and_usage_is_recorded(client, monkeypatch):
    from app.code_review import ai_review

    headers = register(client, "review-ai@example.com")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai_review, "create_provider", lambda _: MockReviewProvider())
    response = client.post(
        "/api/v1/reviews",
        headers=headers,
        json={
            "language": "python",
            "ai_enabled": True,
            "analyzers": ["ruff"],
            "files": [{"path": "math.py", "content": "def divide(a, b):\n    return a / b\n"}],
        },
    )
    assert response.status_code == 201, response.text
    review = response.json()
    ai_findings = [item for item in review["findings"] if item["source"] == "ai"]
    assert ai_findings and ai_findings[0]["evidence"].startswith("def divide"), review[
        "configuration"
    ]
    assert ai_findings[0]["reasoning"] == "No zero check is performed."
    history = client.get("/api/v1/ai/usage", headers=headers).json()
    assert any(item["feature"] == "code_review" and item["total_tokens"] == 70 for item in history)


class MockPatchProvider:
    async def generate_structured(self, *, prompt, instructions, response_schema):
        return ProviderResult(
            AIPatchOutput(
                updated_file="def divide(a, b):\n    if b == 0:\n        raise ValueError('zero divisor')\n    return a / b\n",
                explanation="Reject zero divisors.",
            ),
            "openai",
            "mock",
            80,
            40,
            120,
        )

    async def close(self):
        return None


def test_patch_preview_requires_explicit_approval_and_only_updates_upload(client, monkeypatch):
    from app.code_review import patch_generator

    headers = register(client, "review-patch@example.com")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(patch_generator, "create_provider", lambda _: MockPatchProvider())
    created = client.post(
        "/api/v1/reviews",
        headers=headers,
        json={
            "language": "python",
            "ai_enabled": False,
            "analyzers": ["ruff"],
            "files": [
                {
                    "path": "math.py",
                    "content": "def divide(a, b):\n    unused = 3\n    return a / b\n",
                }
            ],
        },
    )
    assert created.status_code == 201
    review = created.json()
    original_content = "def divide(a, b):\n    unused = 3\n    return a / b\n"
    finding = next((item for item in review["findings"] if item["source"] == "static"), None)
    assert finding is not None, review["configuration"]
    preview = client.post(
        f"/api/v1/reviews/{review['id']}/findings/{finding['id']}/patch", headers=headers
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["unified_diff"].startswith("--- a/math.py")
    rejected = client.post(
        f"/api/v1/reviews/{review['id']}/findings/{finding['id']}/patch/apply",
        headers=headers,
        json={"approved": False},
    )
    assert rejected.status_code == 400
    applied = client.post(
        f"/api/v1/reviews/{review['id']}/findings/{finding['id']}/patch/apply",
        headers=headers,
        json={"approved": True},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"] is True
    rollback = client.post(
        f"/api/v1/reviews/{review['id']}/findings/{finding['id']}/patch/rollback",
        headers=headers,
        json={"approved": True},
    )
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["rolled_back"] is True
    detail = client.get(f"/api/v1/reviews/{review['id']}", headers=headers)
    assert detail.status_code == 200
    source = next(item for item in detail.json()["files"] if item["path"] == "math.py")
    # The detail endpoint intentionally returns hashes only; the preview must now match
    # the original content hash after rollback.
    import hashlib

    assert source["sha256"] == hashlib.sha256(original_content.encode()).hexdigest()


def test_project_ownership_is_checked_for_review(client):
    owner = register(client, "review-project-owner@example.com")
    outsider = register(client, "review-project-outsider@example.com")
    project = client.post("/api/v1/projects", headers=owner, json={"name": "private"}).json()
    response = client.post(
        "/api/v1/reviews",
        headers=outsider,
        json={
            "project_id": project["id"],
            "language": "python",
            "ai_enabled": False,
            "files": [{"path": "x.py", "content": "x = 1"}],
        },
    )
    assert response.status_code == 404
