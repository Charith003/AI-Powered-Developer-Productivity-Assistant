from app.ai.exceptions import AIConfigurationError
from app.ai.providers.base import AIProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.config import Settings


def create_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider.lower() != "openai":
        raise AIConfigurationError(
            f"Unsupported AI_PROVIDER '{settings.ai_provider}'. Configure AI_PROVIDER=openai."
        )
    if not settings.openai_api_key:
        raise AIConfigurationError()
    return OpenAIProvider(settings)
