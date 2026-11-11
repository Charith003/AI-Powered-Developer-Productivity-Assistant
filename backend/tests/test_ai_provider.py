import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, RateLimitError
from pydantic import BaseModel

from app.ai.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIRateLimitError,
    AIStructuredOutputError,
    AITimeoutError,
)
from app.ai.provider_factory import create_provider
from app.ai.providers.openai_provider import OpenAIProvider
from app.ai.usage_tracker import estimate_cost
from app.config import ModelPricing, Settings


class Output(BaseModel):
    value: str


def configured_settings(**overrides):
    values = {
        "jwt_secret": "test-secret-that-is-longer-than-thirty-two-characters",
        "database_url": "sqlite+pysqlite:///:memory:",
        "openai_api_key": "test-key",
        "ai_max_retries": 0,
    }
    values.update(overrides)
    return Settings(**values)


def response(parsed=None):
    return SimpleNamespace(
        output_parsed=parsed,
        model="gpt-5.5",
        usage=SimpleNamespace(input_tokens=11, output_tokens=7, total_tokens=18),
    )


def provider_with(client, settings=None):
    return OpenAIProvider(settings or configured_settings(), client=client)


class FakeClient:
    def __init__(self, result=None, side_effect=None):
        self.responses = SimpleNamespace(
            parse=AsyncMock(return_value=result, side_effect=side_effect)
        )
        self.close = AsyncMock()


def test_provider_factory_requires_key_and_supports_openai():
    with pytest.raises(AIConfigurationError):
        create_provider(configured_settings(openai_api_key=None))
    provider = create_provider(configured_settings())
    assert isinstance(provider, OpenAIProvider)
    asyncio.run(provider.close())
    with pytest.raises(AIConfigurationError, match="Unsupported AI_PROVIDER"):
        create_provider(configured_settings(ai_provider="unknown"))


def test_openai_provider_parses_pydantic_and_extracts_usage():
    client = FakeClient(result=response(Output(value="valid")))
    result = asyncio.run(
        provider_with(client).generate_structured(
            prompt="question", instructions="answer", response_schema=Output
        )
    )
    assert result.parsed.value == "valid"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (11, 7, 18)
    assert client.responses.parse.await_args.kwargs["store"] is False


def test_invalid_structured_output_is_reported():
    with pytest.raises(AIStructuredOutputError):
        asyncio.run(
            provider_with(FakeClient(result=response())).generate_structured(
                prompt="question", instructions="answer", response_schema=Output
            )
        )


def test_rate_limit_retries_are_bounded(monkeypatch):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    limited = RateLimitError("rate limited", response=httpx.Response(429, request=request), body={})
    client = FakeClient(side_effect=[limited, response(Output(value="recovered"))])
    settings = configured_settings(ai_max_retries=1)
    monkeypatch.setattr("app.ai.providers.openai_provider.asyncio.sleep", AsyncMock())
    result = asyncio.run(
        provider_with(client, settings).generate_structured(
            prompt="question", instructions="answer", response_schema=Output
        )
    )
    assert result.parsed.value == "recovered"
    assert client.responses.parse.await_count == 2


def test_rate_limit_and_timeout_stop_at_retry_limit(monkeypatch):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    limited = RateLimitError("rate limited", response=httpx.Response(429, request=request), body={})
    timed_out = APITimeoutError(request=request)
    monkeypatch.setattr("app.ai.providers.openai_provider.asyncio.sleep", AsyncMock())
    client = FakeClient(side_effect=[limited, limited, limited])
    with pytest.raises(AIRateLimitError):
        asyncio.run(
            provider_with(client, configured_settings(ai_max_retries=2)).generate_structured(
                prompt="question", instructions="answer", response_schema=Output
            )
        )
    assert client.responses.parse.await_count == 3
    timeout_client = FakeClient(side_effect=timed_out)
    with pytest.raises(AITimeoutError):
        asyncio.run(
            provider_with(timeout_client).generate_structured(
                prompt="question", instructions="answer", response_schema=Output
            )
        )
    assert timeout_client.responses.parse.await_count == 1


def test_provider_errors_are_normalized_without_leaking_details():
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    error = APIConnectionError(message="secret-looking transport detail", request=request)
    client = FakeClient(side_effect=error)
    with pytest.raises(AIProviderError) as captured:
        asyncio.run(
            provider_with(client).generate_structured(
                prompt="private prompt", instructions="answer", response_schema=Output
            )
        )
    assert "private prompt" not in str(captured.value)


def test_cost_estimate_uses_configured_model_pricing_only():
    settings = configured_settings(
        ai_model_pricing_json={
            "gpt-5.5": ModelPricing(input_per_million="1", output_per_million="2")
        }
    )
    assert estimate_cost(settings, "gpt-5.5", 10, 5) == Decimal("0.000020")
    assert estimate_cost(settings, "unknown-model", 10, 5) is None
