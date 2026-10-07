import re
from time import perf_counter
from typing import Any

from app.agents.base import BaseAgent
from app.prompts.loader import load_prompt
from app.schemas.common import AgentResult, AgentStatus
from app.schemas.review import (
    ReviewerBrief,
    ReviewerBriefFinding,
    ReviewerBriefInput,
    ReviewerSupplierSummary,
    ReviewPackage,
)
from app.utils.masking import mask_account_number

_CODE_TOKEN = re.compile(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b")
_FORBIDDEN_DECISION_LANGUAGE = re.compile(
    r"\b(?:approve|approved|approval|reject|rejected|rejection|request rework|"
    r"risk score|risk label|risk\s+(?:is|level)|score\s*(?:is|of|:)?\s*\d+|"
    r"hard[- ]block(?:ed|s)?|blocked|next workflow action|approver|stage|status|"
    r"low risk|medium risk|high risk)\b",
    re.IGNORECASE,
)
_QUOTED_TEXT = re.compile(r'(?:"[^"]+"|“[^”]+”)')


class HumanReviewAgent(BaseAgent[ReviewPackage, ReviewPackage]):
    """Generate explanatory reviewer context only; approval remains a human action."""

    name = "human_review"

    def run(self, input: ReviewPackage | dict[str, Any]) -> AgentResult[ReviewPackage]:
        package = ReviewPackage.model_validate(input)
        started = perf_counter()
        request = self._mask_input(self._brief_input(package))
        prompt = load_prompt(
            "reviewer_brief", review_context=request.model_dump_json(indent=2)
        )
        response = self._call_llm(
            system=(
                "Write reviewer context only. Do not make or imply an approve, reject, "
                "rework, stage, status, risk score, risk label, hard-block, or approver "
                "decision. Use only supplied facts. Do not quote or invent evidence."
            ),
            user=prompt,
            schema=ReviewerBrief,
            key="reviewer_brief",
        )
        warnings: list[str] = []
        if response is None:
            response = self._fallback(request)
            warnings.append("Reviewer brief used the deterministic fallback; human review remains available.")
        else:
            response, warning = self._sanitize(response, request)
            if warning:
                response = self._fallback(request)
                warnings.append(warning)
        completed_package = package.model_copy(
            update={"reviewer_brief": response.reviewer_brief}
        )
        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.OK,
            data=completed_package,
            warnings=warnings,
            duration_ms=round((perf_counter() - started) * 1000),
        )

    @staticmethod
    def _brief_input(package: ReviewPackage) -> ReviewerBriefInput:
        return ReviewerBriefInput(
            supplier_summary=ReviewerSupplierSummary(
                request_type=package.supplier_summary.request_type,
                supplier_name=package.supplier_summary.supplier_name,
                legal_name=package.supplier_summary.legal_name,
                country=package.supplier_summary.country,
                estimated_annual_spend=package.supplier_summary.estimated_annual_spend,
            ),
            extracted_fields=package.extracted_fields,
            findings=[
                ReviewerBriefFinding(
                    code=item.code,
                    severity=item.severity.value,
                    message=item.message,
                )
                for item in package.validation_findings
            ],
            verification_summary=package.verification_summary,
            evidence=package.evidence,
        )

    @staticmethod
    def _mask_input(value: ReviewerBriefInput) -> ReviewerBriefInput:
        fields = []
        for item in value.extracted_fields:
            field_value = item.value
            if "account" in item.field_name.casefold() or "iban" in item.field_name.casefold():
                field_value = mask_account_number(str(field_value)) if field_value is not None else None
            fields.append(
                item.model_copy(
                    update={
                        "value": field_value,
                        "evidence": [
                            evidence.model_copy(update={"quote": _mask_labeled_accounts(evidence.quote)})
                            for evidence in item.evidence
                        ],
                    }
                )
            )
        return value.model_copy(
            update={
                "extracted_fields": fields,
                "findings": [
                    item.model_copy(update={"message": _mask_labeled_accounts(item.message)})
                    for item in value.findings
                ],
                "evidence": [
                    item.model_copy(update={"quote": _mask_labeled_accounts(item.quote)})
                    for item in value.evidence
                ],
            }
        )

    @staticmethod
    def _sanitize(
        response: ReviewerBrief, request: ReviewerBriefInput
    ) -> tuple[ReviewerBrief, str | None]:
        text = _mask_labeled_accounts(response.reviewer_brief).strip()
        if _FORBIDDEN_DECISION_LANGUAGE.search(text):
            return response, "Dropped reviewer brief that attempted to make or imply an approval/workflow decision."
        if _QUOTED_TEXT.search(text):
            return response, "Dropped reviewer brief containing an unverified evidence quotation."
        known = {item.code.value for item in request.findings}
        allowed = known | {
            "LOCAL_SIMULATED", "LIVE", "VERIFIED", "UNAVAILABLE", "NOT_CONFIGURED",
            "NOT_FOUND", "MISMATCH",
        }
        unknown_codes = {token for token in _CODE_TOKEN.findall(text) if token not in allowed}
        if unknown_codes:
            return response, (
                "Dropped reviewer brief with unknown finding code(s): "
                + ", ".join(sorted(unknown_codes))
                + "."
            )
        if any(item.mode.value == "LOCAL_SIMULATED" for item in request.verification_summary):
            text = (
                "LOCAL_SIMULATED checks are simulations and do not represent live government, "
                "bank, or sanctions verification. " + text
            ).strip()
        return ReviewerBrief(reviewer_brief=text), None

    @staticmethod
    def _fallback(request: ReviewerBriefInput) -> ReviewerBrief:
        supplier = (
            request.supplier_summary.legal_name
            or request.supplier_summary.supplier_name
            or "this supplier"
        )
        if request.findings:
            details = "Findings to examine: " + "; ".join(
                f"{item.code.value}: {item.message}" for item in request.findings
            )
        else:
            details = "No deterministic validation findings were supplied. Review the source records."
        simulated = any(
            item.mode.value == "LOCAL_SIMULATED" for item in request.verification_summary
        )
        provenance = (
            " LOCAL_SIMULATED checks are simulations and do not represent live government, bank, "
            "or sanctions verification."
            if simulated else ""
        )
        return ReviewerBrief(
            reviewer_brief=(
                f"Review the submitted information for {supplier}. {details}{provenance} "
                "Use the attached source evidence to resolve outstanding questions."
            )
        )


def _mask_labeled_accounts(value: str) -> str:
    pattern = re.compile(
        r"(?i)(\b(?:account\s*(?:number|no\.?|#)|a/c\s*(?:number|no\.?|#)|iban)\s*[:#-]?)"
        r"((?:\d[ -]?){7,30}\d|[A-Z0-9][A-Z0-9-]{7,33})"
    )
    return pattern.sub(
        lambda match: f"{match.group(1)}{mask_account_number(match.group(2))}", value
    )
