from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.integrations.base import VerificationResult


class BankVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_number: str
    routing_code: str
    account_holder_name: str
    bank_name: str | None = None
    country: str
    currency: str | None = None


class BankVerificationResult(VerificationResult):
    account_active: bool | None = None
    resolved_bank_name: str | None = None
    holder_name_match_score: float | None = None


class RoutingLookupResult(VerificationResult):
    resolved_bank_name: str | None = None


class BankVerificationProvider(Protocol):
    def verify_account(
        self, account_number: str, routing_code: str, account_holder_name: str,
        bank_name: str | None, country: str, currency: str | None,
    ) -> BankVerificationResult: ...

    def lookup_routing_code(self, routing_code: str) -> RoutingLookupResult: ...
