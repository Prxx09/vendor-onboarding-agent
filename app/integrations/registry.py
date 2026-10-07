from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.integrations.base import VerificationResult


class CompanyVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    registration_number: str
    legal_name: str
    country: str


class CompanyVerificationResult(VerificationResult):
    registered_name: str | None = None
    active: bool | None = None
    incorporation_date: date | None = None
    registered_address: str | None = None
    name_match_score: float | None = None


class BusinessRegistryProvider(Protocol):
    def verify_company(
        self, registration_number: str, legal_name: str, country: str
    ) -> CompanyVerificationResult: ...
