from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    @abstractmethod
    def generate_structured(
        self, *, system: str, user: str, schema: type[T], key: str | None = None
    ) -> T:
        raise NotImplementedError
