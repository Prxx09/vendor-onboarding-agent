from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.base import VerificationResult


class SanctionsScreeningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    aliases: list[str] = Field(default_factory=list)
    country: str


class SanctionsMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    list_name: str
    score: float


class SanctionsResult(VerificationResult):
    matches: list[SanctionsMatch] = Field(default_factory=list)


class SanctionsScreeningProvider(Protocol):
    def screen(self, name: str, aliases: list[str], country: str) -> SanctionsResult: ...
