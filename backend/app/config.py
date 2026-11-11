from decimal import Decimal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelPricing(BaseModel):
    input_per_million: Decimal = Field(ge=0)
    output_per_million: Decimal = Field(ge=0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DevPilot AI API"
    environment: str = "development"
    frontend_origin: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://devpilot:devpilot@localhost:5432/devpilot"
    jwt_secret: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    openai_api_key: str | None = None
    ai_provider: str = "openai"
    openai_model: str = "gpt-5.5"
    openai_embedding_model: str = "text-embedding-3-small"
    ai_request_timeout: float = Field(default=30.0, gt=0, le=180)
    ai_max_retries: int = Field(default=2, ge=0, le=5)
    ai_max_output_tokens: int = Field(default=4000, ge=1, le=16000)
    ai_model_pricing_json: dict[str, ModelPricing] = Field(default_factory=dict)
    checkstyle_jar: str | None = None
    checkstyle_config: str | None = None
    test_sandbox_image: str | None = None
    test_sandbox_timeout_seconds: int = Field(default=30, ge=1, le=120)
    test_sandbox_memory: str = "256m"
    test_sandbox_cpus: str = "1.0"
    test_sandbox_pids: int = Field(default=64, ge=16, le=256)
    test_sandbox_output_bytes: int = Field(default=65_536, ge=4096, le=262_144)

    def validate_auth_configuration(self) -> None:
        if len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must contain at least 32 characters")
        if self.environment == "production" and self.database_url.startswith("sqlite"):
            raise RuntimeError(
                "SQLite is not supported in production; configure PostgreSQL DATABASE_URL"
            )


settings = Settings()
