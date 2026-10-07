from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    NOT_FOUND = "NOT_FOUND"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class VerificationMode(StrEnum):
    LOCAL_SIMULATED = "LOCAL_SIMULATED"
    LIVE = "LIVE"


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: str
    provider_name: str
    mode: VerificationMode
    status: VerificationStatus
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reference_id: str | None = None
    latency_ms: int = 0
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    def to_record(self, request_id: str):
        from app.schemas.domain import VerificationResultRecord

        values = self.model_dump(mode="json")
        normalized = {
            key: value for key, value in values.items()
            if key not in {"capability", "provider_name", "mode", "status", "checked_at",
                           "reference_id", "latency_ms", "error", "details"}
            and value is not None
        }
        return VerificationResultRecord(
            request_id=request_id, capability=self.capability, provider_name=self.provider_name,
            mode=self.mode.value, status=self.status.value, reference_id=self.reference_id,
            details={**self.details, "normalized": normalized}, latency_ms=self.latency_ms,
            error=self.error, checked_at=self.checked_at,
        )
