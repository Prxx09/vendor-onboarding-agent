from abc import ABC, abstractmethod
from time import perf_counter
from typing import Generic, TypeVar

from pydantic import BaseModel

from app.llm.base import LLMProvider, T
from app.llm.errors import LLMError
from app.schemas.common import AgentResult, AgentStatus

InT = TypeVar("InT")
OutT = TypeVar("OutT", bound=BaseModel)


class BaseAgent(ABC, Generic[InT, OutT]):
    name: str

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    @abstractmethod
    def run(self, input: InT) -> AgentResult[OutT]:
        raise NotImplementedError

    def _call_llm(self, *, system: str, user: str, schema: type[T], key: str | None = None) -> T | None:
        try:
            return self.provider.generate_structured(system=system, user=user, schema=schema, key=key)
        except LLMError:
            return None

    @staticmethod
    def _duration(start: float) -> int:
        return int((perf_counter() - start) * 1000)

    def _failure(self, start: float, error: str) -> AgentResult[OutT]:
        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.NEEDS_MANUAL_REVIEW,
            data=None,
            error=error,
            duration_ms=self._duration(start),
        )
