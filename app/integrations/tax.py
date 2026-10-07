from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.integrations.base import VerificationResult


class TaxVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tax_id: str
    country: str
    legal_name: str


class TaxVerificationResult(VerificationResult):
    registered_legal_name: str | None = None
    tax_status: str | None = None
    registered_address: str | None = None
    name_match_score: float | None = None


class TaxIdVerificationProvider(Protocol):
    def verify_tax_id(self, tax_id: str, country: str, legal_name: str) -> TaxVerificationResult: ...
