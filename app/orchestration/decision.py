from collections.abc import Iterable

from app.schemas.assessment import ExtractionOutcome, NextAction
from app.schemas.findings import Finding, FindingCode
from app.schemas.risk import RiskResult


def decide_next_action(
    extraction_status: ExtractionOutcome | str,
    findings: Iterable[Finding],
    risk_result: RiskResult,
    pending_field_review: bool,
    *,
    missing_required_fields: Iterable[str] = (),
) -> tuple[NextAction, list[str]]:
    """Apply the Phase 5 priority order without consulting storage or an LLM."""
    codes = {finding.code for finding in findings}
    outcome = str(extraction_status)
    missing_required_fields = tuple(missing_required_fields)
    if outcome in {ExtractionOutcome.FAILED.value, ExtractionOutcome.UNUSABLE.value}:
        return NextAction.MANUAL_REVIEW, [
            "Document extraction failed or produced unusable text; manual review is required."
        ]

    if risk_result.blocked or risk_result.hard_blocks:
        blocked = ", ".join(code.value for code in risk_result.hard_blocks)
        return NextAction.BLOCKED, [f"A deterministic hard block is present: {blocked}."]

    if (
        FindingCode.MISSING_REQUIRED_DOCUMENT in codes
        or FindingCode.EXPIRED_DOCUMENT in codes
        or bool(missing_required_fields)
    ):
        reasons = []
        if FindingCode.MISSING_REQUIRED_DOCUMENT in codes:
            reasons.append("A required document is missing.")
        if FindingCode.EXPIRED_DOCUMENT in codes:
            reasons.append("A required document is expired.")
        missing = sorted(set(missing_required_fields))
        if missing:
            reasons.append(f"Required extracted fields are missing or unverified: {', '.join(missing)}.")
        return NextAction.REQUEST_REWORK, reasons

    if FindingCode.VERIFICATION_UNAVAILABLE in codes:
        return NextAction.MANUAL_REVIEW, [
            "A verification provider was unavailable; its result cannot be treated as verified."
        ]

    if pending_field_review and FindingCode.LOW_CONFIDENCE_FIELD in codes:
        return NextAction.MANUAL_REVIEW, [
            "A low-confidence field is still pending human review."
        ]

    return NextAction.PROCEED_TO_APPROVAL, [
        "Deterministic checks found no blocker requiring rework or manual review; eligible for human approval review."
    ]
