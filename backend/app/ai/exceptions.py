class AIServiceError(Exception):
    code = "ai_provider_error"
    message = "The AI provider request failed. Please try again later."
    http_status = 502
    usage_status = "provider_error"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.message)
        self.message = message or self.message


class AIConfigurationError(AIServiceError):
    code = "ai_not_configured"
    message = "AI is not configured. Set OPENAI_API_KEY on the backend, then restart the API."
    http_status = 503
    usage_status = "configuration_error"


class AIRateLimitError(AIServiceError):
    code = "ai_rate_limited"
    message = "The AI provider is rate limiting requests. Please try again shortly."
    http_status = 429
    usage_status = "rate_limited"


class AITimeoutError(AIServiceError):
    code = "ai_timeout"
    message = "The AI provider took too long to respond. Please try again."
    http_status = 504
    usage_status = "timeout"


class AIProviderError(AIServiceError):
    pass


class AIStructuredOutputError(AIServiceError):
    code = "ai_invalid_output"
    message = "The AI provider returned output that did not match the required response format."
    http_status = 502
    usage_status = "invalid_output"
