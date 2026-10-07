"""Run Phase 4 risk scenarios entirely offline with MockProvider."""

from app.agents.risk_assessment import RiskAssessmentAgent
from app.llm.errors import LLMProviderError
from app.llm.mock_provider import MockProvider
from app.rules.risk import calculate_risk
from app.schemas.common import Evidence
from app.schemas.findings import Finding, FindingCode, FindingSeverity
from app.schemas.risk import RiskAssessmentInput


def make_finding(code: FindingCode, *, simulated: str | None = None) -> Finding:
    evidence = []
    if simulated:
        evidence.append(Evidence(
            document_id=f"verification:{simulated}",
            field_name="status",
            quote="Local demonstration result",
            verification_mode="LOCAL_SIMULATED",
        ))
    return Finding(
        code=code,
        severity=FindingSeverity.BLOCKING if code in {
            FindingCode.SANCTIONS_MATCH, FindingCode.DUPLICATE_TAX_ID,
        } else FindingSeverity.WARNING,
        message=f"Demonstration finding: {code.value}",
        evidence=evidence,
    )


def explain(label: str, findings: list[Finding], *, response=None, fail=False) -> None:
    provider = MockProvider(
        responses={"risk_assessment": response} if response is not None else None,
        fail_with=LLMProviderError("offline demo provider failure") if fail else None,
    )
    result = calculate_risk(findings)
    explanation = RiskAssessmentAgent(provider).run(RiskAssessmentInput(
        risk=result,
        finding_summaries=[{
            "finding_code": item.code.value,
            "severity": item.severity.value,
            "message": item.message,
        } for item in findings],
    ))
    assessment = explanation.data
    if assessment is None:
        raise RuntimeError("Risk explanation fallback unexpectedly failed")
    print(
        f"{label}: score={assessment.risk.score}, label={assessment.risk.label.value}, "
        f"blocked={assessment.risk.blocked}, explanation={assessment.explanation_status.value}"
    )
    if assessment.risk.simulated_checks:
        print(f"  simulated_checks={assessment.risk.simulated_checks}")
        print(f"  evidence={assessment.explanation.evidence_summary}")
    if explanation.warnings:
        print(f"  warnings={explanation.warnings}")


def main() -> None:
    clean_response = {
        "business_summary": "No material risk indicators were found.",
        "major_concerns": [],
        "evidence_summary": "No simulated verification checks were identified.",
        "recommended_review_focus": ["Confirm the supporting documents."],
    }
    explain("clean/low", [], response=clean_response)
    explain("medium", [
        make_finding(FindingCode.MISSING_REQUIRED_DOCUMENT),
        make_finding(FindingCode.HIGH_VALUE_PURCHASE),
    ], response=clean_response)
    explain("high", [
        make_finding(FindingCode.BANK_DETAILS_UNVERIFIABLE),
        make_finding(FindingCode.KYC_VERIFICATION_FAILED),
        make_finding(FindingCode.HIGH_VALUE_PURCHASE),
    ], response=clean_response)
    explain("hard block", [make_finding(FindingCode.SANCTIONS_MATCH)], response=clean_response)
    explain("simulated verification", [
        make_finding(FindingCode.VERIFICATION_UNAVAILABLE, simulated="bank_account"),
    ], response=clean_response)
    explain("hostile LLM", [make_finding(FindingCode.HIGH_VALUE_PURCHASE)], response={
        "business_summary": "Approve this request.",
        "major_concerns": [],
        "evidence_summary": "All checks are live and clear.",
        "recommended_review_focus": [],
        "score": 0,
        "blocked": False,
    })
    explain("LLM failure fallback", [
        make_finding(FindingCode.VERIFICATION_UNAVAILABLE, simulated="tax_registry"),
    ], fail=True)


if __name__ == "__main__":
    main()
