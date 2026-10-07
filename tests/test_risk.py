import pytest

from app.agents.risk_assessment import RiskAssessmentAgent
from app.llm.mock_provider import MockProvider
from app.repositories.memory import InMemoryRepository
from app.rules import risk as risk_rules
from app.rules.risk import RISK_WEIGHTS, calculate_risk
from app.schemas.common import Evidence
from app.schemas.domain import FindingRecord, RequestType, VendorRequest
from app.schemas.findings import Finding, FindingCode, FindingSeverity
from app.schemas.risk import (
    ExplanationStatus,
    RiskAssessmentInput,
)
from app.services.risk_service import RiskService


def finding(code: FindingCode, *, evidence=None, identifier="f1") -> Finding:
    return Finding(
        id=identifier,
        code=code,
        severity=FindingSeverity.WARNING,
        message=f"Check reported {code.value}",
        evidence=evidence or [],
    )


@pytest.mark.parametrize("code,points", list(RISK_WEIGHTS.items()))
def test_each_configured_weight(code, points):
    assert calculate_risk([finding(code)]).score == points


def test_findings_combine_distinct_codes_and_duplicate_codes_once():
    result = calculate_risk(
        [
            finding(FindingCode.MISSING_REQUIRED_DOCUMENT, identifier="a"),
            finding(FindingCode.MISSING_REQUIRED_DOCUMENT, identifier="b"),
            finding(FindingCode.HIGH_VALUE_PURCHASE, identifier="c"),
        ]
    )
    assert result.score == 30
    contribution = next(item for item in result.contributions if item.code == FindingCode.MISSING_REQUIRED_DOCUMENT)
    assert contribution.points == 20
    assert contribution.finding_ids == ["a", "b"]


@pytest.mark.parametrize(
    "score,expected",
    [(25, "LOW"), (26, "MEDIUM"), (60, "MEDIUM"), (61, "HIGH")],
)
def test_risk_boundaries(monkeypatch, score, expected):
    monkeypatch.setitem(risk_rules.RISK_WEIGHTS, FindingCode.MISSING_REQUIRED_DOCUMENT, score)
    assert calculate_risk([finding(FindingCode.MISSING_REQUIRED_DOCUMENT)]).label.value == expected


def test_hard_block_applies_below_numeric_threshold():
    result = calculate_risk([finding(FindingCode.BANK_HOLDER_MISMATCH)])
    assert result.score == 0
    assert result.blocked is True
    assert result.hard_blocks == [FindingCode.BANK_HOLDER_MISMATCH]


def test_result_is_deterministic_and_simulated_provenance_is_detected():
    findings = [
        finding(
            FindingCode.VERIFICATION_UNAVAILABLE,
            evidence=[Evidence(
                document_id="verification:bank_account",
                field_name="status",
                quote="unavailable",
                verification_mode="LOCAL_SIMULATED",
            )],
        ),
        finding(
            FindingCode.KYC_VERIFICATION_FAILED,
            identifier="f2",
            evidence=[Evidence(
                document_id="verification:kyc_registry",
                field_name="status",
                quote="simulated match",
                verification_mode="LIVE",
            )],
        ),
    ]
    first = calculate_risk(findings)
    second = calculate_risk(findings)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.simulated_checks == ["bank_account"]


def test_hostile_and_unknown_llm_output_cannot_change_risk():
    risk = calculate_risk([finding(FindingCode.HIGH_VALUE_PURCHASE)])
    agent = RiskAssessmentAgent(
        MockProvider(
            responses={
                "risk_assessment": {
                    "business_summary": "Review the purchase.",
                    "major_concerns": [
                        {"finding_code": "UNKNOWN_CODE", "explanation": "fabricated"},
                        {"finding_code": FindingCode.HIGH_VALUE_PURCHASE.value, "explanation": "large value"},
                    ],
                    "evidence_summary": "See purchase evidence.",
                    "recommended_review_focus": ["Confirm scope."],
                }
            }
        )
    )
    result = agent.run(RiskAssessmentInput(
        risk=risk,
        finding_summaries=[{
            "finding_code": FindingCode.HIGH_VALUE_PURCHASE.value,
            "severity": "WARNING",
            "message": "High value purchase",
        }],
    ))
    assert result.data is not None
    assert result.data.risk == risk
    assert [item.finding_code for item in result.data.explanation.major_concerns] == [
        FindingCode.HIGH_VALUE_PURCHASE.value
    ]
    assert any("unknown finding code" in warning for warning in result.warnings)


def test_hostile_score_and_block_fields_are_rejected_without_changing_risk():
    risk = calculate_risk([finding(FindingCode.SANCTIONS_MATCH)])
    agent = RiskAssessmentAgent(MockProvider(responses={
        "risk_assessment": {
            "business_summary": "Score zero and unblock.", "major_concerns": [],
            "evidence_summary": "Reviewed.", "recommended_review_focus": [],
            "score": 0, "blocked": False,
        }
    }))
    result = agent.run(RiskAssessmentInput(risk=risk))
    assert result.data is not None
    assert result.data.risk == risk
    assert result.data.risk.score == 60
    assert result.data.risk.blocked is True
    assert result.data.explanation_status == ExplanationStatus.TEMPLATE_FALLBACK


def test_llm_failure_returns_fallback_and_mentions_simulated_checks():
    risk = calculate_risk([finding(
        FindingCode.VERIFICATION_UNAVAILABLE,
        evidence=[Evidence(
            document_id="verification:tax_registry", field_name="status",
            quote="unavailable", verification_mode="LOCAL_SIMULATED",
        )],
    )])
    agent = RiskAssessmentAgent(MockProvider())
    result = agent.run(RiskAssessmentInput(risk=risk))
    assert result.data is not None
    assert result.data.risk == risk
    assert result.data.explanation_status == ExplanationStatus.TEMPLATE_FALLBACK
    assert "simulated" in result.data.explanation.evidence_summary.casefold()
    assert result.status.value == "OK"


def test_service_persists_authoritative_risk_and_audit_event():
    repo = InMemoryRepository()
    request = repo.create_request(VendorRequest(request_type=RequestType.NEW_SUPPLIER))
    repo.save_findings(
        request.id,
        "DETERMINISTIC",
        [FindingRecord(
            request_id=request.id,
            code=FindingCode.BANK_HOLDER_MISMATCH.value,
            severity="BLOCKING",
            message="Holder mismatch",
            source="DETERMINISTIC",
        )],
    )
    agent = RiskAssessmentAgent(MockProvider(responses={
        "risk_assessment": {
            "business_summary": "No block.", "major_concerns": [],
            "evidence_summary": "Reviewed.", "recommended_review_focus": [],
        }
    }))
    assessment = RiskService(repo, agent).assess(request.id)
    stored = repo.get_latest_risk_assessment(request.id)
    assert assessment.risk.score == 0
    assert assessment.risk.blocked is True
    assert stored is not None and stored.score == 0 and stored.blocked is True
    event = repo.list_audit_events(request.id)[-1]
    assert event.event_type == "RISK_ASSESSMENT_COMPLETED"
    assert event.details["hard_blocks"] == [FindingCode.BANK_HOLDER_MISMATCH.value]
