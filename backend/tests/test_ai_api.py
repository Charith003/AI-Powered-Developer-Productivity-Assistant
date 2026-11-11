from app.ai.providers.base import ProviderResult
from app.ai.schemas import AIAnswer
from app.config import ModelPricing, settings


def register(client, email):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "AI Test User", "password": "A-strong-password-123"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class SuccessfulProvider:
    async def generate_structured(self, *, prompt, instructions, response_schema):
        assert prompt == "Explain this function"
        return ProviderResult(
            parsed=AIAnswer(answer="It transforms the input.", key_points=["Pure function"]),
            provider="openai",
            model="gpt-5.5",
            input_tokens=20,
            output_tokens=12,
            total_tokens=32,
        )

    async def close(self):
        return None


def test_ai_status_and_missing_key_error_are_safe_and_persisted(client):
    headers = register(client, "ai-missing@example.com")
    assert client.get("/api/v1/ai/status").status_code == 401
    status = client.get("/api/v1/ai/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["available"] is False
    assert status.json()["api_key_configured"] is False
    assert "api_key" not in status.json()
    response = client.post(
        "/api/v1/ai/generate",
        headers=headers,
        json={"prompt": "Sensitive user prompt should not be stored"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_not_configured"
    assert "OPENAI_API_KEY" in response.json()["error"]["message"]
    history = client.get("/api/v1/ai/usage", headers=headers)
    assert history.status_code == 200
    assert history.json()[0]["status"] == "configuration_error"
    assert "prompt" not in history.json()[0]
    summary = client.get("/api/v1/ai/usage/summary", headers=headers)
    assert summary.json()["requests"] == 1
    assert summary.json()["failed_requests"] == 1
    assert summary.json()["total_tokens"] == 0


def test_successful_ai_usage_is_persisted_and_scoped(client, monkeypatch):
    from app.ai import service

    headers = register(client, "ai-success@example.com")
    project = client.post("/api/v1/projects", headers=headers, json={"name": "AI project"}).json()
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        settings,
        "ai_model_pricing_json",
        {"gpt-5.5": ModelPricing(input_per_million="1", output_per_million="2")},
    )
    monkeypatch.setattr(service, "create_provider", lambda _: SuccessfulProvider())
    response = client.post(
        "/api/v1/ai/generate",
        headers=headers,
        json={"prompt": "Explain this function", "project_id": project["id"]},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "It transforms the input."
    history = client.get("/api/v1/ai/usage", headers=headers, params={"project_id": project["id"]})
    assert len(history.json()) == 1
    assert history.json()[0]["project_id"] == project["id"]
    assert history.json()[0]["status"] == "succeeded"
    assert history.json()[0]["total_tokens"] == 32
    assert float(history.json()[0]["estimated_cost_usd"]) == 0.000044
    summary = client.get("/api/v1/ai/usage/summary", headers=headers)
    assert summary.json()["successful_requests"] == 1
    assert summary.json()["total_tokens"] == 32
    other_headers = register(client, "ai-other@example.com")
    assert client.get("/api/v1/ai/usage", headers=other_headers).json() == []
    assert (
        client.get(
            "/api/v1/ai/usage", headers=other_headers, params={"project_id": project["id"]}
        ).status_code
        == 404
    )


def test_generate_rejects_project_owned_by_another_user(client):
    owner = register(client, "ai-owner@example.com")
    outsider = register(client, "ai-outsider@example.com")
    project = client.post("/api/v1/projects", headers=owner, json={"name": "Private"}).json()
    response = client.post(
        "/api/v1/ai/generate",
        headers=outsider,
        json={"prompt": "Do not access this project", "project_id": project["id"]},
    )
    assert response.status_code == 404
    assert client.get("/api/v1/ai/usage", headers=outsider).json() == []
