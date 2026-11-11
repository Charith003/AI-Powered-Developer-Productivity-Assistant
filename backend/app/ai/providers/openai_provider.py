import asyncio
import logging

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from app.ai.exceptions import (
    AIProviderError,
    AIRateLimitError,
    AIStructuredOutputError,
    AITimeoutError,
)
from app.ai.providers.base import AIProvider, ProviderResult
from app.config import Settings

logger = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, settings: Settings, client: AsyncOpenAI | None = None):
        if not settings.openai_api_key:
            raise ValueError("OpenAIProvider requires a configured API key")
        self.settings = settings
        self.model = settings.openai_model
        self.max_retries = settings.ai_max_retries
        self.client = client or AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.ai_request_timeout,
            max_retries=0,
        )

    async def generate_structured(
        self, *, prompt: str, instructions: str, response_schema: type[BaseModel]
    ) -> ProviderResult:
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.responses.parse(
                    model=self.model,
                    input=prompt,
                    instructions=instructions,
                    text_format=response_schema,
                    max_output_tokens=self.settings.ai_max_output_tokens,
                    store=False,
                )
                parsed = response.output_parsed
                if parsed is None:
                    raise AIStructuredOutputError()
                if not isinstance(parsed, response_schema):
                    parsed = response_schema.model_validate(parsed)
                usage = response.usage
                input_tokens = int(usage.input_tokens) if usage else 0
                output_tokens = int(usage.output_tokens) if usage else 0
                total_tokens = (
                    int(usage.total_tokens)
                    if usage and usage.total_tokens is not None
                    else input_tokens + output_tokens
                )
                return ProviderResult(
                    parsed=parsed,
                    provider=self.name,
                    model=response.model or self.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                )
            except AIStructuredOutputError:
                raise
            except ValidationError:
                raise AIStructuredOutputError() from None
            except RateLimitError:
                if attempt >= self.max_retries:
                    raise AIRateLimitError() from None
                logger.warning("AI provider rate limit; retrying attempt=%s", attempt + 1)
                await asyncio.sleep(min(0.5 * (2**attempt), 4.0))
            except APITimeoutError:
                if attempt >= self.max_retries:
                    raise AITimeoutError() from None
                logger.warning("AI provider timeout; retrying attempt=%s", attempt + 1)
                await asyncio.sleep(min(0.5 * (2**attempt), 4.0))
            except APIConnectionError:
                if attempt >= self.max_retries:
                    raise AIProviderError("The AI provider could not be reached.") from None
                logger.warning("AI provider connection error; retrying attempt=%s", attempt + 1)
                await asyncio.sleep(min(0.5 * (2**attempt), 4.0))
            except APIStatusError as exc:
                if exc.status_code >= 500 and attempt < self.max_retries:
                    logger.warning("AI provider server error; retrying attempt=%s", attempt + 1)
                    await asyncio.sleep(min(0.5 * (2**attempt), 4.0))
                    continue
                raise AIProviderError() from None
            except APIError as exc:
                logger.error("AI provider API error type=%s", type(exc).__name__)
                raise AIProviderError() from None
        raise AIProviderError()

    async def close(self) -> None:
        await self.client.close()
