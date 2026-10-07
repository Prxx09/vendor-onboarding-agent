from typing import Any

from app.agents.risk_assessment import RiskAssessmentAgent
from app.repositories.base import OnboardingRepository
from app.rules.config import RulesConfig
from app.rules.risk import calculate_risk
from app.schemas.domain import ActorType, AuditEvent, RiskAssessmentRecord
from app.schemas.findings import Finding
from app.schemas.risk import (
    RiskAssessment,
    RiskAssessmentInput,
    RiskFindingSummary,
)


class RiskService:
    def __init__(
        self,
        repo: OnboardingRepository,
        agent: RiskAssessmentAgent,
        rules_config: RulesConfig | None = None,
    ) -> None:
        self.repo = repo
        self.agent = agent
        self.rules_config = rules_config or RulesConfig()

    def assess(
        self, request_id: str, *, validation_analysis_summary: str = ""
    ) -> RiskAssessment:
        if self.repo.get_request(request_id) is None:
            raise KeyError(f"Request not found: {request_id}")
        records = self.repo.list_findings(request_id)
        findings = [
            Finding.model_validate(
                {
                    "id": record.id,
                    "code": record.code,
                    "severity": record.severity,
                    "message": record.message,
                    "evidence": record.evidence or [],
                    "source": record.source,
                }
            )
            for record in records
        ]
        risk = calculate_risk(findings, self.rules_config)
        request = RiskAssessmentInput(
            risk=risk,
            finding_summaries=[
                RiskFindingSummary(
                    finding_code=finding.code.value,
                    severity=finding.severity.value,
                    message=finding.message,
                )
                for finding in findings
            ],
            validation_analysis_summary=validation_analysis_summary,
        )
        agent_result = self.agent.run(request)
        if agent_result.data is None:
            raise RuntimeError("RiskAssessmentAgent did not return its required explanation fallback")
        # Explicitly retain the calculator output, even if an alternate agent implementation
        # returns a different risk object.
        assessment = RiskAssessment(
            risk=risk,
            explanation=agent_result.data.explanation,
            explanation_status=agent_result.data.explanation_status,
        )
        explanation_payload: dict[str, Any] = assessment.explanation.model_dump(mode="json")
        explanation_payload["explanation_status"] = assessment.explanation_status.value
        record = RiskAssessmentRecord(
            request_id=request_id,
            score=risk.score,
            label=risk.label.value,
            hard_blocks=[code.value for code in risk.hard_blocks],
            contributions=[item.model_dump(mode="json") for item in risk.contributions],
            explanation=explanation_payload,
            blocked=risk.blocked,
            simulated_checks=risk.simulated_checks,
            config_snapshot=risk.config_snapshot,
        )
        latest = self.repo.get_latest_risk_assessment(request_id)
        if latest is None or not self._same_deterministic_result(latest, record):
            self.repo.save_risk_assessment(record)
        self.repo.append_audit_event(
            AuditEvent(
                request_id=request_id,
                actor="risk_service",
                actor_type=ActorType.SYSTEM,
                event_type="RISK_ASSESSMENT_COMPLETED",
                details={
                    "score": risk.score,
                    "label": risk.label.value,
                    "blocked": risk.blocked,
                    "hard_blocks": [code.value for code in risk.hard_blocks],
                    "finding_codes": sorted({finding.code.value for finding in findings}),
                    "explanation_status": assessment.explanation_status.value,
                },
            )
        )
        return assessment

    @staticmethod
    def _same_deterministic_result(
        latest: RiskAssessmentRecord, current: RiskAssessmentRecord
    ) -> bool:
        fields = (
            "score", "label", "hard_blocks", "contributions", "blocked",
            "simulated_checks", "config_snapshot",
        )
        return all(getattr(latest, field) == getattr(current, field) for field in fields)
