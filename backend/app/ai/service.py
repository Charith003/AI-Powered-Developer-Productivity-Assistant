import logging
from time import monotonic

from app.ai.exceptions import AIServiceError
from app.ai.provider_factory import create_provider
from app.ai.providers.base import ProviderResult
from app.ai.schemas import AIAnswer
from app.ai.usage_tracker import UsageTracker
from app.config import Settings
from app.models import AIUsage

logger = logging.getLogger(__name__)
FEATURE = "generate_response"
INSTRUCTIONS = (
    "Answer the user's engineering question accurately and concisely. "
    "Return a short answer, a list of key points, and no unsupported claims."
)


class AIService:
    def __init__(self, db, settings: Settings, provider_factory=None):
        self.db = db
        self.settings = settings
        self.provider_factory = provider_factory or create_provider
        self.usage = UsageTracker(db, settings)

    async def generate_answer(
        self, *, user_id: str, project_id: str | None, prompt: str
    ) -> tuple[AIAnswer, AIUsage]:
        started = monotonic()
        provider = None
        try:
            provider = self.provider_factory(self.settings)
            result: ProviderResult = await provider.generate_structured(
                prompt=prompt,
                instructions=INSTRUCTIONS,
                response_schema=AIAnswer,
            )
        except AIServiceError as exc:
            self.usage.record(
                user_id=user_id,
                project_id=project_id,
                provider=self.settings.ai_provider,
                model=self.settings.openai_model,
                feature=FEATURE,
                status=exc.usage_status,
                duration_ms=max(0, int((monotonic() - started) * 1000)),
            )
            raise
        except Exception as exc:  # noqa: BLE001 - normalize unexpected provider failures without logging content
            logger.error("AI service failure type=%s", type(exc).__name__)
            error = AIServiceError()
            self.usage.record(
                user_id=user_id,
                project_id=project_id,
                provider=self.settings.ai_provider,
                model=self.settings.openai_model,
                feature=FEATURE,
                status=error.usage_status,
                duration_ms=max(0, int((monotonic() - started) * 1000)),
            )
            raise error from None
        finally:
            if provider is not None:
                try:
                    await provider.close()
                except Exception as exc:  # noqa: BLE001 - normalize unexpected provider failures without logging content
                    logger.warning("AI provider close failed type=%s", type(exc).__name__)

        usage = self.usage.record(
            user_id=user_id,
            project_id=project_id,
            provider=result.provider,
            model=result.model,
            feature=FEATURE,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=result.total_tokens,
            status="succeeded",
            duration_ms=max(0, int((monotonic() - started) * 1000)),
        )
        logger.info(
            "AI request completed user_id=%s project_id=%s provider=%s model=%s status=%s tokens=%s duration_ms=%s",
            user_id,
            project_id,
            result.provider,
            result.model,
            usage.status,
            usage.total_tokens,
            usage.duration_ms,
        )
        return AIAnswer.model_validate(result.parsed), usage
