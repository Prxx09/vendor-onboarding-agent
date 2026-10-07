from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.base import VerificationMode, VerificationStatus
from app.rules.document_fields import DocumentType
from app.schemas.common import Evidence
from app.schemas.domain import ExtractedStatus, ReviewStatus
from app.schemas.findings import Finding
from app.schemas.risk import RiskAssessment
from app.schemas.validation_analysis import ValidationAnalysisResult


class NextAction(StrEnum):
    PROCEED_TO_APPROVAL = "PROCEED_TO_APPROVAL"
    REQUEST_REWORK = "REQUEST_REWORK"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    BLOCKED = "BLOCKED"


class ExtractionOutcome(StrEnum):
    NOT_RUN = "NOT_RUN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNUSABLE = "UNUSABLE"


class AssessedExtractedField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    document_type: DocumentType
    field_name: str
    value: Any | None = None
    confidence: float | None = None
    status: ExtractedStatus
    review_status: ReviewStatus
    evidence: list[Evidence] = Field(default_factory=list)


class VerificationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: str
    provider_name: str
    mode: VerificationMode
    status: VerificationStatus


class AgentAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    extraction_status: ExtractionOutcome
    extracted_data: list[AssessedExtractedField] = Field(default_factory=list)
    validation_findings: list[Finding] = Field(default_factory=list)
    validation_analysis: ValidationAnalysisResult
    risk_assessment: RiskAssessment
    verification_summary: list[VerificationSummary] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    recommended_next_action: NextAction
    human_review_required: Literal[True] = True
    reasons: list[str] = Field(default_factory=list)
    explanation: str
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


