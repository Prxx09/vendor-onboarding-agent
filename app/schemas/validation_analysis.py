from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.findings import Finding


class ValidationRequestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    request_type: str
    supplier_name: str | None = None
    legal_name: str | None = None
    country: str | None = None
    estimated_annual_spend: str | None = None


class ExtractedSummaryField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: str
    field_name: str
    value: Any | None = None
    confidence: float | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class ValidationAnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_summary: ValidationRequestSummary
    extracted_summary: list[ExtractedSummaryField]
    findings: list[Finding]


class FindingExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    explanation: str
    evidence_refs: list[str] = Field(default_factory=list)


class RelatedIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_ids: list[str]
    note: str


class AgentObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    evidence_refs: list[str] = Field(default_factory=list)


class ValidationAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    finding_explanations: list[FindingExplanation] = Field(default_factory=list)
    related_issues: list[RelatedIssue] = Field(default_factory=list)
    agent_observations: list[AgentObservation] = Field(default_factory=list)
    recommended_review_actions: list[str] = Field(default_factory=list)
