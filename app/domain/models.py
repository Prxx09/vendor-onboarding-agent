from typing import Any, Literal

from pydantic import BaseModel, Field


DocumentType = Literal[
    "business_registration",
    "tax_certificate",
    "bank_proof",
    "other",
]

CheckStatus = Literal[
    "VERIFIED",
    "NOT_FOUND",
    "MISMATCH",
    "REVIEW_REQUIRED",
    "ERROR",
]


class DocumentExtraction(BaseModel):
    filename: str = ""
    document_type: DocumentType
    confidence: float = Field(ge=0.0, le=1.0)

    legal_name: str | None = None
    registration_number: str | None = None
    tax_id: str | None = None

    account_holder_name: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    ifsc_swift: str | None = None

    registered_address: str | None = None
    issue_date: str | None = None
    expiry_date: str | None = None

    notes: list[str] = Field(default_factory=list)


class VerificationEvidence(BaseModel):
    source: str
    status: CheckStatus
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class AgentEvent(BaseModel):
    step: str
    message: str


class VendorProcessResult(BaseModel):
    vendor_id: str
    vendor_name: str
    overall_status: Literal["APPROVED", "ACTION_REQUIRED", "REVIEW_REQUIRED"]
    recommendation: Literal["APPROVE", "WAIT_FOR_DOCUMENTS", "REJECT"]
    missing_documents: list[str] = Field(default_factory=list)
    extractions: list[DocumentExtraction] = Field(default_factory=list)
    checks: list[VerificationEvidence] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    events: list[AgentEvent] = Field(default_factory=list)


class HumanReviewRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    reviewer: str
    comment: str = ""
