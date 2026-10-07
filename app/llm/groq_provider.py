import json
import logging
import time
from typing import Any

from groq import Groq
from pydantic import ValidationError

from app.config import Settings
from app.llm.base import LLMProvider, T
from app.llm.errors import LLMOutputError, LLMProviderError

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        if client is None and not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        self.settings = settings
        self.client = client or Groq(
            api_key=settings.groq_api_key, timeout=settings.groq_timeout_seconds
        )

    def generate_structured(
        self, *, system: str, user: str, schema: type[T], key: str | None = None
    ) -> T:
        system_prompt = f"{system}\n\nReturn only strict JSON matching this JSON Schema:\n{json.dumps(schema.model_json_schema())}"
        correction = ""
        for validation_attempt in range(2):
            try:
                raw = self._request(system_prompt + correction, user)
            except Exception as exc:  # noqa: BLE001 - normalize SDK and transport failures
                self._raise_provider_error(exc)
            try:
                return schema.model_validate_json(raw)
            except (ValidationError, ValueError, TypeError) as exc:
                if validation_attempt == 1:
                    raise LLMOutputError(
                        f"Groq output failed {schema.__name__} validation after retry"
                    ) from exc
                correction = f"\nYour previous response failed validation: {exc}. Return corrected JSON only."
        raise LLMOutputError("Groq output validation failed")

    def _request(self, system: str, user: str) -> str:
        retries = max(0, self.settings.groq_max_retries)
        for attempt in range(retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.settings.groq_model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=0,
                    response_format={"type": "json_object"},
                    timeout=self.settings.groq_timeout_seconds,
                )
                content = response.choices[0].message.content
                if not isinstance(content, str):
                    raise TypeError("Provider returned empty content")
                return content
            except Exception as exc:
                if attempt >= retries or not self._is_transient(exc):
                    raise
                logger.warning("Groq transient request failure; retry=%d", attempt + 1)
                time.sleep(min(0.1 * (attempt + 1), 0.5))
        raise RuntimeError("Groq request exhausted retries")

    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        return status is None or status == 429 or status >= 500

    @staticmethod
    def _raise_provider_error(exc: Exception) -> None:
        if isinstance(exc, LLMOutputError):
            raise exc
        logger.error("Groq provider request failed (%s)", type(exc).__name__)
        raise LLMProviderError("Groq provider request failed") from exc
