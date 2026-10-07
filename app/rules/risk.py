"""Pure deterministic risk scoring. Finding codes are counted once per request."""

from collections import defaultdict
from collections.abc import Iterable

from app.rules.config import RulesConfig
from app.schemas.common import Evidence
from app.schemas.findings import Finding, FindingCode
from app.schemas.risk import RiskContribution, RiskLabel, RiskResult

# Assumptions: duplicate bank account and KYC verification failure each contribute 30.
# VERIFICATION_UNAVAILABLE contributes 0 because it forces manual review in the
# orchestrator rather than increasing the score.
RISK_WEIGHTS: dict[FindingCode, int] = {
    FindingCode.MISSING_REQUIRED_DOCUMENT: 20,
    FindingCode.EXPIRED_DOCUMENT: 20,
    FindingCode.SIMILAR_SUPPLIER_NAME: 20,
    FindingCode.CROSS_DOCUMENT_INCONSISTENCY: 20,
    FindingCode.BANK_DETAILS_UNVERIFIABLE: 30,
    FindingCode.DUPLICATE_TAX_ID: 40,
    FindingCode.SANCTIONS_MATCH: 60,
    FindingCode.HIGH_VALUE_PURCHASE: 10,
    FindingCode.LOW_CONFIDENCE_FIELD: 10,
    FindingCode.DUPLICATE_BANK_ACCOUNT: 30,
    FindingCode.KYC_VERIFICATION_FAILED: 30,
    FindingCode.VERIFICATION_UNAVAILABLE: 0,
}

HARD_BLOCK_CODES = frozenset({
    FindingCode.SANCTIONS_MATCH,
    FindingCode.DUPLICATE_TAX_ID,
    FindingCode.BANK_HOLDER_MISMATCH,
    FindingCode.BANK_NAME_MISMATCH,
})


def classify_risk_score(score: int, config: RulesConfig) -> RiskLabel:
    if score <= config.risk_low_max:
        return RiskLabel.LOW
    if score <= config.risk_medium_max:
        return RiskLabel.MEDIUM
    return RiskLabel.HIGH


def calculate_risk(findings: Iterable[Finding], config: RulesConfig | None = None) -> RiskResult:
    """Score distinct finding codes once, independent of storage or external services."""
    rules = config or RulesConfig()
    grouped: dict[FindingCode, list[str]] = defaultdict(list)
    simulated: set[str] = set()
    for item in findings:
        grouped[item.code].append(item.id)
        simulated.update(_simulated_capabilities(item.evidence))

    contributions = [
        RiskContribution(
            code=code, points=RISK_WEIGHTS.get(code, 0), finding_ids=sorted(set(grouped[code]))
        )
        for code in sorted(grouped, key=lambda value: value.value)
    ]
    score = sum(item.points for item in contributions)
    present_codes = set(grouped)
    hard_blocks = sorted(present_codes & HARD_BLOCK_CODES, key=lambda value: value.value)
    config_snapshot = {
        "weights": {code.value: RISK_WEIGHTS.get(code, 0) for code in FindingCode},
        "risk_low_max": rules.risk_low_max,
        "risk_medium_max": rules.risk_medium_max,
        "hard_block_codes": sorted(code.value for code in HARD_BLOCK_CODES),
        "counting_rule": "Each distinct finding code contributes its weight once per request.",
    }
    return RiskResult(
        score=score,
        label=classify_risk_score(score, rules),
        hard_blocks=hard_blocks,
        blocked=bool(hard_blocks),
        contributions=contributions,
        simulated_checks=sorted(simulated),
        config_snapshot=config_snapshot,
    )


def _simulated_capabilities(evidence: list[Evidence]) -> set[str]:
    capabilities = set()
    for item in evidence:
        if item.verification_mode != "LOCAL_SIMULATED":
            continue
        prefix = "verification:"
        if item.document_id.startswith(prefix):
            capabilities.add(item.document_id.removeprefix(prefix))
    return capabilities
