class LLMError(Exception):
    """Base exception for controlled LLM failures."""


class LLMProviderError(LLMError):
    """Provider/network failure."""


class LLMOutputError(LLMError):
    """The provider returned output that failed schema validation."""


class MockResponseNotConfigured(LLMError):
    """No mock response is configured for a request."""
