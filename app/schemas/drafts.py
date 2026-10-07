from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.base import VerificationMode, VerificationStatus
from app.schemas.domain import (
    Approval,
    ExtractedFieldRecord,
    FindingRecord,
    VendorRequest,
    VerificationResultRecord,
)


class DraftVerificationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: str
    provider: str
    mode: VerificationMode
    status: VerificationStatus


class SourceFieldReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    field_id: str
    field_name: str


class VendorBankDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bank_name: str | None = None
    branch: str | None = None
    account_number_masked: str | None = None
    routing_code: str | None = None
    currency: str | None = None


class VendorDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    legal_name: str | None = None
    trading_name: str | None = None
    tax_id: str | None = None
    registration_number: str | None = None
    address: str | None = None
    country: str | None = None
    supplier_category: str | None = None
    contact: str | None = None
    bank: VendorBankDraft = Field(default_factory=VendorBankDraft)
    payment_terms: str | None = None
    approval_references: list[str] = Field(default_factory=list)
    source_field_references: list[SourceFieldReference] = Field(default_factory=list)
    verification_status: list[DraftVerificationStatus] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    status: Literal["DRAFT"] = "DRAFT"
    version: int = Field(default=1, ge=1)


class PODraftLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    quantity: Decimal = Field(ge=0)
    unit_price: Decimal = Field(ge=0)
    tax: Decimal = Field(ge=0)
    line_total: Decimal = Field(ge=0)


class PODraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    draft_po_reference: str
    supplier: str
    line_items: list[PODraftLineItem] = Field(default_factory=list)
    currency: str | None = None
    subtotal: Decimal = Field(ge=0)
    tax_total: Decimal = Field(ge=0)
    total: Decimal = Field(ge=0)
    payment_terms: str | None = None
    delivery_date: date | None = None
    approval_references: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    status: Literal["DRAFT"] = "DRAFT"
    version: int = Field(default=1, ge=1)


class VendorDraftInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    request: VendorRequest
    fields: list[ExtractedFieldRecord] = Field(default_factory=list)
    verifications: list[VerificationResultRecord] = Field(default_factory=list)
    approvals: list[Approval] = Field(default_factory=list)
    findings: list[FindingRecord] = Field(default_factory=list)
    version: int = Field(ge=1)


class PODraftInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    request: VendorRequest
    fields: list[ExtractedFieldRecord] = Field(default_factory=list)
    approvals: list[Approval] = Field(default_factory=list)
    findings: list[FindingRecord] = Field(default_factory=list)
    version: int = Field(ge=1)
