from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.rules.document_fields import DocumentType
from app.schemas.common import Evidence


class ExtractedFieldStatus(StrEnum):
    FOUND = "FOUND"
    MISSING = "MISSING"
    UNVERIFIED = "UNVERIFIED"


class LLMExtractedField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: Any | None = None
    evidence_quote: str | None = None


class LLMLineItemValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any | None = None
    evidence_quote: str | None = None


class LLMLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: LLMLineItemValue = Field(default_factory=LLMLineItemValue)
    quantity: LLMLineItemValue = Field(default_factory=LLMLineItemValue)
    unit_price: LLMLineItemValue = Field(default_factory=LLMLineItemValue)
    tax: LLMLineItemValue = Field(default_factory=LLMLineItemValue)


class LLMExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    fields: list[LLMExtractedField] = Field(default_factory=list)
    line_items: list[LLMLineItem] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class ExtractedField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: Any | None
    status: ExtractedFieldStatus
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: Evidence | None = None
    needs_review: bool = False


class ExtractedLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: ExtractedField
    quantity: ExtractedField
    unit_price: ExtractedField
    tax: ExtractedField


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    document_type: DocumentType
    fields: list[ExtractedField]
    line_items: list[ExtractedLineItem] = Field(default_factory=list)
    missing_required_fields: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    needs_manual_review: bool
