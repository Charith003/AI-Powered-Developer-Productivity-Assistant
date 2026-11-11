from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AIUsage


def estimate_cost(
    settings: Settings, model: str, input_tokens: int, output_tokens: int
) -> Decimal | None:
    pricing = settings.ai_model_pricing_json.get(model)
    if pricing is None:
        return None
    return (
        Decimal(input_tokens) * pricing.input_per_million
        + Decimal(output_tokens) * pricing.output_per_million
    ) / Decimal(1_000_000)


class UsageTracker:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def record(
        self,
        *,
        user_id: str,
        project_id: str | None,
        provider: str,
        model: str,
        feature: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        status: str,
        duration_ms: int,
    ) -> AIUsage:
        usage = AIUsage(
            user_id=user_id,
            project_id=project_id,
            provider=provider,
            model=model,
            feature=feature,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimate_cost(self.settings, model, input_tokens, output_tokens),
            status=status,
            duration_ms=duration_ms,
        )
        self.db.add(usage)
        self.db.commit()
        self.db.refresh(usage)
        return usage
