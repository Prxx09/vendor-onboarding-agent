from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Evidence


class FindingCode(StrEnum):
    MISSING_REQUIRED_DOCUMENT = "MISSING_REQUIRED_DOCUMENT"
    EXPIRED_DOCUMENT = "EXPIRED_DOCUMENT"
    SIMILAR_SUPPLIER_NAME = "SIMILAR_SUPPLIER_NAME"
    CROSS_DOCUMENT_INCONSISTENCY = "CROSS_DOCUMENT_INCONSISTENCY"
    BANK_DETAILS_UNVERIFIABLE = "BANK_DETAILS_UNVERIFIABLE"
    BANK_HOLDER_MISMATCH = "BANK_HOLDER_MISMATCH"
    BANK_NAME_MISMATCH = "BANK_NAME_MISMATCH"
    DUPLICATE_TAX_ID = "DUPLICATE_TAX_ID"
    DUPLICATE_BANK_ACCOUNT = "DUPLICATE_BANK_ACCOUNT"
    SANCTIONS_MATCH = "SANCTIONS_MATCH"
    HIGH_VALUE_PURCHASE = "HIGH_VALUE_PURCHASE"
    LOW_CONFIDENCE_FIELD = "LOW_CONFIDENCE_FIELD"
    INVALID_TAX_ID_FORMAT = "INVALID_TAX_ID_FORMAT"
    MISSING_BUDGET_OWNER = "MISSING_BUDGET_OWNER"
    QUOTATION_REQUIRED = "QUOTATION_REQUIRED"
    HIGH_RISK_COUNTRY = "HIGH_RISK_COUNTRY"


class FindingSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    code: FindingCode
    severity: FindingSeverity
    message: str
    evidence: list[Evidence] = Field(default_factory=list)
    source: str = "DETERMINISTIC"
    related_vendor_id: str | None = None
