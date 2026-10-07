from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def now_utc() -> datetime:
    return datetime.now(UTC)


class RequestType(StrEnum):
    NEW_SUPPLIER = "NEW_SUPPLIER"
    SUPPLIER_WITH_PURCHASE = "SUPPLIER_WITH_PURCHASE"


class ExtractedStatus(StrEnum):
    FOUND = "FOUND"
    MISSING = "MISSING"
    UNVERIFIED = "UNVERIFIED"


class ReviewStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CORRECTED = "CORRECTED"


class ApprovalStage(StrEnum):
    PROCUREMENT = "PROCUREMENT"
    BUDGET_OWNER = "BUDGET_OWNER"
    FINANCE_HEAD = "FINANCE_HEAD"


class ApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_REWORK = "REQUEST_REWORK"


class ActorType(StrEnum):
    AGENT = "AGENT"
    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=now_utc)


class VendorRequest(Record):
    request_type: RequestType
    status: str = "DRAFT"
    supplier_name: str | None = None
    legal_name: str | None = None
    country: str | None = None
    tax_id: str | None = None
    address: str | None = None
    currency: str | None = None
    estimated_annual_spend: Decimal | None = None
    requesting_department: str | None = None
    requester_id: str | None = None
    budget_owner_id: str | None = None
    procurement_owner_id: str | None = None
    purchase_details: dict[str, Any] | None = None
    is_demo: bool = False
    updated_at: datetime = Field(default_factory=now_utc)


class Document(Record):
    request_id: str
    doc_type: str
    file_name: str
    storage_path: str
    sha256: str | None = None
    text_content: str | None = None
    text_quality: dict[str, Any] | None = None


class ExtractedFieldRecord(Record):
    request_id: str
    document_id: str
    field_name: str
    value: Any = None
    confidence: Decimal | None = None
    status: ExtractedStatus
    evidence: dict[str, Any] | list[Any] | None = None
    review_status: ReviewStatus = ReviewStatus.PENDING
    reviewed_by: str | None = None


class FindingRecord(Record):
    request_id: str
    code: str
    severity: str
    message: str
    evidence: dict[str, Any] | list[Any] | None = None
    source: str


class VerificationResultRecord(Record):
    request_id: str
    capability: str
    provider_name: str
    mode: str
    status: str
    reference_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0
    error: str | None = None
    checked_at: datetime = Field(default_factory=now_utc)


class RiskAssessmentRecord(Record):
    request_id: str
    score: int
    label: str
    hard_blocks: dict[str, Any] | list[Any] = Field(default_factory=list)
    contributions: dict[str, Any] | list[Any] = Field(default_factory=list)
    explanation: dict[str, Any] = Field(default_factory=dict)
    blocked: bool = False
    simulated_checks: list[str] = Field(default_factory=list)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)


class Approval(Record):
    request_id: str
    stage: ApprovalStage
    approver_id: str
    approver_role: str | None = None
    decision: ApprovalDecision | None = None
    comment: str | None = None


class AuditEvent(Record):
    model_config = ConfigDict(from_attributes=True, frozen=True)
    request_id: str | None = None
    actor: str
    actor_type: ActorType
    event_type: str
    details: dict[str, Any] = Field(default_factory=dict)


class AgentRun(Record):
    request_id: str
    agent_name: str
    status: str
    input_hash: str
    output: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int


class Vendor(Record):
    legal_name: str
    tax_id: str | None = None
    country: str | None = None
    address: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    routing_code: str | None = None
    status: str | None = None


class SanctionsEntry(Record):
    name: str
    aliases: list[str] = Field(default_factory=list)
    country: str | None = None
    list_name: str


class VendorDraftRecord(Record):
    request_id: str
    draft: dict[str, Any]
    version: int = 1


class PODraftRecord(Record):
    request_id: str
    draft: dict[str, Any]
    version: int = 1
