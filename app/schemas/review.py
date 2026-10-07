from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.base import VerificationMode, VerificationStatus
from app.rules.document_fields import DocumentType
from app.schemas.assessment import NextAction
from app.schemas.common import Evidence
from app.schemas.domain import ApprovalStage, ExtractedStatus, ReviewStatus
from app.schemas.findings import Finding, FindingCode
from app.schemas.risk import RiskLabel
from app.workflow.states import WorkflowStatus


class ReviewSupplierSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_type: str
    supplier_name: str | None = None
    legal_name: str | None = None
    country: str | None = None
    estimated_annual_spend: str | None = None
    request_status: WorkflowStatus


class ReviewExtractedField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    document_type: DocumentType
    field_name: str
    value: Any | None = None
    confidence: float | None = None
    status: ExtractedStatus
    review_status: ReviewStatus
    evidence: list[Evidence] = Field(default_factory=list)


class ReviewVerificationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: str
    provider_name: str
    mode: VerificationMode
    status: VerificationStatus


class HumanDecisionType(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_REWORK = "REQUEST_REWORK"


class ApproverRole(StrEnum):
    PROCUREMENT = "PROCUREMENT"
    BUDGET_OWNER = "BUDGET_OWNER"
    FINANCE_HEAD = "FINANCE_HEAD"


class HumanDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: ApprovalStage
    approver_id: str
    approver_role: ApproverRole
    decision: HumanDecisionType
    comment: str


class NextRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: WorkflowStatus
    next_stage: ApprovalStage | None = None
    message: str


class ReviewHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_at: datetime
    event_type: str
    actor: str
    actor_type: str
    summary: str


class ReviewPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    request_status: WorkflowStatus
    supplier_summary: ReviewSupplierSummary
    extracted_fields: list[ReviewExtractedField] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    validation_findings: list[Finding] = Field(default_factory=list)
    risk_score: int
    risk_label: RiskLabel
    hard_blocks: list[FindingCode] = Field(default_factory=list)
    explanation: str
    verification_summary: list[ReviewVerificationSummary] = Field(default_factory=list)
    recommended_next_action: NextAction | None = None
    required_stages: list[ApprovalStage] = Field(default_factory=list)
    completed_stages: list[ApprovalStage] = Field(default_factory=list)
    reviewer_brief: str
    recommended_review_actions: list[str] = Field(default_factory=list)
    next_recommendation: NextRecommendation
    allowed_decisions: list[HumanDecisionType] = Field(default_factory=list)
    history: list[ReviewHistoryEntry] = Field(default_factory=list)


class ReviewerBriefFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: FindingCode
    severity: str
    message: str


class ReviewerSupplierSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_type: str
    supplier_name: str | None = None
    legal_name: str | None = None
    country: str | None = None
    estimated_annual_spend: str | None = None


class ReviewerBriefInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_summary: ReviewerSupplierSummary
    extracted_fields: list[ReviewExtractedField] = Field(default_factory=list)
    findings: list[ReviewerBriefFinding] = Field(default_factory=list)
    verification_summary: list[ReviewVerificationSummary] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class ReviewerBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_brief: str
