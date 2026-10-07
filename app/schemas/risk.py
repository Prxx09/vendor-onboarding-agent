from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.findings import FindingCode


class RiskLabel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ExplanationStatus(StrEnum):
    LLM_EXPLAINED = "LLM_EXPLAINED"
    TEMPLATE_FALLBACK = "TEMPLATE_FALLBACK"


class RiskContribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: FindingCode
    points: int
    finding_ids: list[str] = Field(default_factory=list)


class RiskResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int
    label: RiskLabel
    hard_blocks: list[FindingCode] = Field(default_factory=list)
    blocked: bool
    contributions: list[RiskContribution] = Field(default_factory=list)
    simulated_checks: list[str] = Field(default_factory=list)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)


class RiskConcern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_code: str
    explanation: str


class RiskExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_summary: str
    major_concerns: list[RiskConcern] = Field(default_factory=list)
    evidence_summary: str
    recommended_review_focus: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk: RiskResult
    explanation: RiskExplanation
    explanation_status: ExplanationStatus


class RiskFindingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_code: str
    severity: str
    message: str


class RiskAssessmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk: RiskResult
    finding_summaries: list[RiskFindingSummary] = Field(default_factory=list)
    validation_analysis_summary: str = ""
