from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel


class Evidence(BaseModel):
    document_id: str
    field_name: str
    quote: str
    page: int | None = None
    verification_mode: str | None = None


class AgentStatus(StrEnum):
    OK = "OK"
    NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW"
    FAILED = "FAILED"


T = TypeVar("T")


class AgentResult(BaseModel, Generic[T]):
    agent_name: str
    status: AgentStatus
    data: T | None = None
    warnings: list[str] = []
    error: str | None = None
    duration_ms: int
