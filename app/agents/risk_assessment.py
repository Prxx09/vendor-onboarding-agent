import re
from time import perf_counter
from typing import Any

from app.agents.base import BaseAgent
from app.prompts.loader import load_prompt
from app.schemas.common import AgentResult, AgentStatus
from app.schemas.risk import (
    RiskAssessment,
    RiskAssessmentInput,
    RiskConcern,
    RiskExplanation,
)
from app.utils.masking import mask_account_number


class RiskAssessmentAgent(BaseAgent[RiskAssessmentInput, RiskAssessment]):
    """Explain fixed deterministic risk data; this agent has no scoring authority."""

    name = "risk_assessment"

    def run(self, input: RiskAssessmentInput | dict[str, Any]) -> AgentResult[RiskAssessment]:
        request = RiskAssessmentInput.model_validate(input)
        started = perf_counter()
        request = self._safe_input(request)
        prompt = load_prompt("risk_explanation", risk_context=request.model_dump_json(indent=2))
        explanation = self._call_llm(
            system=(
                "Explain the supplied deterministic risk result only. The score, label, "
                "hard blocks, blocked state, contributions and findings are fixed facts. "
                "Never calculate or change them. Describe simulated checks as simulated. "
                "Only cite finding codes present in the input."
            ),
            user=prompt,
            schema=RiskExplanation,
            key="risk_assessment",
        )
        warnings: list[str] = []
        if explanation is None:
            explanation = self._fallback(request)
            status = "TEMPLATE_FALLBACK"
            warnings.append("LLM explanation unavailable; deterministic risk is preserved.")
        else:
            explanation, warnings = self._sanitize(explanation, request)
            status = "LLM_EXPLAINED"
        assessment = RiskAssessment(
            risk=request.risk,
            explanation=explanation,
            explanation_status=status,
        )
        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.OK,
            data=assessment,
            warnings=warnings,
            duration_ms=round((perf_counter() - started) * 1000),
        )

    @staticmethod
    def _safe_input(request: RiskAssessmentInput) -> RiskAssessmentInput:
        safe_findings = [
            item.model_copy(update={"message": _mask_labeled_accounts(item.message)})
            for item in request.finding_summaries
        ]
        return request.model_copy(
            update={
                "finding_summaries": safe_findings,
                "validation_analysis_summary": _mask_labeled_accounts(
                    request.validation_analysis_summary
                ),
            }
        )

    @staticmethod
    def _sanitize(
        explanation: RiskExplanation, request: RiskAssessmentInput
    ) -> tuple[RiskExplanation, list[str]]:
        known_codes = {item.finding_code for item in request.finding_summaries}
        concerns: list[RiskConcern] = []
        warnings: list[str] = []
        for concern in explanation.major_concerns:
            if concern.finding_code not in known_codes:
                warnings.append(f"Dropped concern for unknown finding code: {concern.finding_code}")
                continue
            concerns.append(
                concern.model_copy(update={"explanation": _mask_labeled_accounts(concern.explanation)})
            )
        evidence_summary = explanation.evidence_summary
        if request.risk.simulated_checks:
            marker = ", ".join(request.risk.simulated_checks)
            if "no simulated" in evidence_summary.casefold():
                evidence_summary = ""
            evidence_summary = (
                f"LOCAL_SIMULATED verification checks: {marker}; these are simulated, "
                f"not live confirmations. {evidence_summary}"
            ).strip()
        return explanation.model_copy(
            update={
                "business_summary": _mask_labeled_accounts(explanation.business_summary),
                "major_concerns": concerns,
                "evidence_summary": _mask_labeled_accounts(evidence_summary),
                "recommended_review_focus": [
                    _mask_labeled_accounts(item) for item in explanation.recommended_review_focus
                ],
            }
        ), warnings

    @staticmethod
    def _fallback(request: RiskAssessmentInput) -> RiskExplanation:
        risk = request.risk
        if risk.blocked:
            summary = (
                f"The request is blocked by {', '.join(code.value for code in risk.hard_blocks)} "
                f"with a deterministic {risk.label.value.lower()} risk score of {risk.score}."
            )
        else:
            summary = (
                f"The deterministic risk score is {risk.score} ({risk.label.value}). "
                "Review the findings before proceeding."
            )
        concerns = [
            RiskConcern(finding_code=item.finding_code, explanation=item.message)
            for item in request.finding_summaries
            if item.finding_code in {contribution.code.value for contribution in risk.contributions}
        ]
        if risk.simulated_checks:
            evidence = (
                "Verification is simulated for: " + ", ".join(risk.simulated_checks)
                + ". These results are not live external confirmations."
            )
        else:
            evidence = "No simulated verification checks were identified in the supplied findings."
        return RiskExplanation(
            business_summary=summary,
            major_concerns=concerns,
            evidence_summary=evidence,
            recommended_review_focus=[
                "Review each deterministic finding and its supporting evidence.",
                *(["Confirm simulated checks through the approved review process."] if risk.simulated_checks else []),
            ],
        )


def _mask_labeled_accounts(value: str) -> str:
    return re.sub(
        r"(?i)(\b(?:account\s*(?:number|no\.?|#)|a/c\s*(?:number|no\.?|#)|iban)\s*[:#-]?\s*)"
        r"((?:\d[ -]?){7,30}\d|[A-Z0-9][A-Z0-9-]{7,33})",
        lambda match: f"{match.group(1)}{mask_account_number(match.group(2))}",
        value,
    )
