import re
from time import perf_counter
from typing import Any

from app.agents.base import BaseAgent
from app.prompts.loader import load_prompt
from app.schemas.common import AgentResult, AgentStatus
from app.schemas.findings import Finding
from app.schemas.validation_analysis import (
    AgentObservation,
    FindingExplanation,
    RelatedIssue,
    ValidationAnalysisInput,
    ValidationAnalysisResult,
)
from app.utils.masking import mask_account_number


class ValidationAnalysisAgent(BaseAgent[ValidationAnalysisInput, ValidationAnalysisResult]):
    name = "validation_analysis"

    def run(
        self, input: ValidationAnalysisInput | dict[str, Any]
    ) -> AgentResult[ValidationAnalysisResult]:
        request = ValidationAnalysisInput.model_validate(input)
        started = perf_counter()
        safe_input = self._mask_input(request)
        prompt = load_prompt(
            "validation_analysis",
            analysis_input=safe_input.model_dump_json(indent=2),
        )
        llm_result = self._call_llm(
            system=(
                "You explain deterministic validation results only. Do not add, remove, "
                "or alter findings or make approval, risk, or workflow decisions."
            ),
            user=prompt,
            schema=ValidationAnalysisResult,
            key="validation_analysis",
        )
        if llm_result is None:
            fallback = self._fallback(safe_input.findings)
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.OK,
                data=fallback,
                warnings=["LLM analysis unavailable; deterministic findings are preserved."],
                duration_ms=round((perf_counter() - started) * 1000),
            )
        sanitized, warnings = self._validate_references(llm_result, safe_input.findings)
        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.OK,
            data=sanitized,
            warnings=warnings,
            duration_ms=round((perf_counter() - started) * 1000),
        )

    @staticmethod
    def _mask_input(value: ValidationAnalysisInput) -> ValidationAnalysisInput:
        extracted = []
        for field in value.extracted_summary:
            field_value = field.value
            if "account" in field.field_name.casefold() or "iban" in field.field_name.casefold():
                field_value = mask_account_number(str(field_value)) if field_value is not None else None
            extracted.append(field.model_copy(update={"value": field_value}))
        findings = []
        for finding in value.findings:
            evidence = []
            for item in finding.evidence:
                quote = item.quote
                if "account" in item.field_name.casefold() or "iban" in item.field_name.casefold():
                    quote = mask_account_number(quote) or ""
                else:
                    quote = _mask_labeled_accounts(quote)
                evidence.append(item.model_copy(update={"quote": quote}))
            findings.append(
                finding.model_copy(
                    update={
                        "message": _mask_labeled_accounts(finding.message),
                        "evidence": evidence,
                    }
                )
            )
        return value.model_copy(update={"extracted_summary": extracted, "findings": findings})

    @staticmethod
    def _validate_references(
        result: ValidationAnalysisResult, findings: list[Finding]
    ) -> tuple[ValidationAnalysisResult, list[str]]:
        finding_ids = {finding.id for finding in findings}
        evidence_refs = {
            f"{evidence.document_id}:{evidence.field_name}"
            for finding in findings
            for evidence in finding.evidence
        }
        warnings: list[str] = []
        explanations: list[FindingExplanation] = []
        for explanation in result.finding_explanations:
            if explanation.finding_id not in finding_ids:
                warnings.append(f"Dropped explanation for unknown finding ID: {explanation.finding_id}")
                continue
            valid_refs = [ref for ref in explanation.evidence_refs if ref in evidence_refs]
            if len(valid_refs) != len(explanation.evidence_refs):
                warnings.append(f"Dropped unknown evidence references for finding {explanation.finding_id}")
            explanations.append(explanation.model_copy(update={"evidence_refs": valid_refs}))

        related_issues: list[RelatedIssue] = []
        for issue in result.related_issues:
            valid_ids = [identifier for identifier in issue.finding_ids if identifier in finding_ids]
            if len(valid_ids) != len(issue.finding_ids):
                warnings.append("Dropped unknown finding IDs from a related-issues note")
            if valid_ids:
                related_issues.append(issue.model_copy(update={"finding_ids": valid_ids}))

        observations: list[AgentObservation] = []
        for observation in result.agent_observations:
            if re.search(r"\b(sanction\w*|duplicat\w*)\b", observation.text, re.IGNORECASE):
                warnings.append("Dropped advisory observation asserting a sanctions or duplicate match")
                continue
            valid_refs = [ref for ref in observation.evidence_refs if ref in evidence_refs]
            if len(valid_refs) != len(observation.evidence_refs):
                warnings.append("Dropped unknown evidence references from an advisory observation")
            observations.append(observation.model_copy(update={"evidence_refs": valid_refs}))

        safe_result = result.model_copy(
            update={
                "summary": _mask_labeled_accounts(result.summary),
                "finding_explanations": explanations,
                "related_issues": related_issues,
                "agent_observations": observations,
                "recommended_review_actions": [
                    _mask_labeled_accounts(item) for item in result.recommended_review_actions
                ],
            }
        )
        return safe_result, warnings

    @staticmethod
    def _fallback(findings: list[Finding]) -> ValidationAnalysisResult:
        explanations = [
            FindingExplanation(
                finding_id=item.id,
                explanation=f"Deterministic validation reported {item.code.value}: {item.message}",
                evidence_refs=[
                    f"{evidence.document_id}:{evidence.field_name}" for evidence in item.evidence
                ],
            )
            for item in findings
        ]
        return ValidationAnalysisResult(
            summary=(
                f"Validation produced {len(findings)} deterministic finding(s). "
                "LLM explanation was unavailable."
            ),
            finding_explanations=explanations,
            recommended_review_actions=["Review the deterministic findings and their cited evidence."],
        )


def _mask_labeled_accounts(value: str) -> str:
    return re.sub(
        r"(?i)(\b(?:account\s*(?:number|no\.?|#)|a/c\s*(?:number|no\.?|#)|iban)\s*[:#-]?\s*)"
        r"((?:\d[ -]?){7,30}\d|[A-Z0-9][A-Z0-9-]{7,33})",
        lambda match: f"{match.group(1)}{mask_account_number(match.group(2))}",
        value,
    )
