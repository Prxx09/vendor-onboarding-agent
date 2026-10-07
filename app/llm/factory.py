from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.groq_provider import GroqProvider
from app.llm.mock_provider import MockProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "groq":
        return GroqProvider(settings)
    return MockProvider()
