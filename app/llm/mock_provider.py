from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from app.llm.base import LLMProvider, T
from app.llm.errors import LLMOutputError, MockResponseNotConfigured

MockValue = dict[str, Any] | BaseModel | Callable[..., Any]


class MockProvider(LLMProvider):
    def __init__(
        self, responses: dict[str, MockValue] | None = None, fail_with: Exception | None = None
    ) -> None:
        self.responses = responses or {}
        self.fail_with = fail_with
        self.calls: list[dict[str, str | None]] = []

    def generate_structured(
        self, *, system: str, user: str, schema: type[T], key: str | None = None
    ) -> T:
        self.calls.append(
            {"system": system, "user": user, "schema": schema.__name__, "key": key}
        )
        if self.fail_with:
            raise self.fail_with
        response_key = key or schema.__name__
        if response_key not in self.responses:
            raise MockResponseNotConfigured(f"No mock response configured for {response_key}")
        value = self.responses[response_key]
        if callable(value):
            value = value(system=system, user=user, schema=schema, key=key)
        if isinstance(value, schema):
            return value
        try:
            return schema.model_validate(value)
        except (ValidationError, TypeError, ValueError) as exc:
            raise LLMOutputError(f"Mock response failed {schema.__name__} validation") from exc
