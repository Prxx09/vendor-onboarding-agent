import pytest

from app.agents.risk_assessment import RiskAssessmentAgent
from app.agents.validation_analysis import ValidationAnalysisAgent
from app.integrations.base import VerificationMode, VerificationStatus
from app.llm.mock_provider import MockProvider
from app.orchestration.decision import decide_next_action
from app.repositories.memory import InMemoryRepository
from app.rules.risk import calculate_risk
from app.schemas.assessment import ExtractionOutcome, NextAction
from app.schemas.common import AgentResult, AgentStatus, Evidence
from app.schemas.domain import (
    Document,
    ExtractedFieldRecord,
    ExtractedStatus,
    FindingRecord,
    RequestType,
    ReviewStatus,
    VendorRequest,
    VerificationResultRecord,
)
from app.schemas.extraction import ExtractedField, ExtractedFieldStatus, ExtractionResult
from app.schemas.findings import Finding, FindingCode, FindingSeverity
from app.services.orchestration_service import OnboardingOrchestrator
from app.services.risk_service import RiskService


def make_finding(code: FindingCode, evidence=None) -> Finding:
    return Finding(
        code=code,
        severity=FindingSeverity.BLOCKING if code in {
            FindingCode.SANCTIONS_MATCH, FindingCode.DUPLICATE_TAX_ID,
            FindingCode.BANK_HOLDER_MISMATCH, FindingCode.BANK_NAME_MISMATCH,
        } else FindingSeverity.WARNING,
        message=f"Finding: {code.value}",
        evidence=evidence or [],
    )


def result_for(code: FindingCode | None = None):
    findings = [make_finding(code)] if code else []
    return calculate_risk(findings)


@pytest.mark.parametrize(
    "outcome,codes,blocked,pending,missing,expected",
    [
        (ExtractionOutcome.COMPLETED, [], False, False, [], NextAction.PROCEED_TO_APPROVAL),
        (ExtractionOutcome.COMPLETED, [FindingCode.MISSING_REQUIRED_DOCUMENT], False, False, [], NextAction.REQUEST_REWORK),
        (ExtractionOutcome.COMPLETED, [FindingCode.EXPIRED_DOCUMENT], False, False, [], NextAction.REQUEST_REWORK),
        (ExtractionOutcome.COMPLETED, [], False, False, ["tax_id"], NextAction.REQUEST_REWORK),
        (ExtractionOutcome.COMPLETED, [FindingCode.LOW_CONFIDENCE_FIELD], False, True, [], NextAction.MANUAL_REVIEW),
        (ExtractionOutcome.COMPLETED, [FindingCode.VERIFICATION_UNAVAILABLE], False, False, [], NextAction.MANUAL_REVIEW),
        (ExtractionOutcome.COMPLETED, [FindingCode.SANCTIONS_MATCH], True, False, [], NextAction.BLOCKED),
        (ExtractionOutcome.FAILED, [FindingCode.SANCTIONS_MATCH], True, False, [], NextAction.MANUAL_REVIEW),
        (ExtractionOutcome.UNUSABLE, [], False, False, [], NextAction.MANUAL_REVIEW),
    ],
)
def test_decision_outcomes_and_priority(outcome, codes, blocked, pending, missing, expected):
    findings = [make_finding(code) for code in codes]
    risk = calculate_risk(findings)
    if blocked and not risk.blocked:
        # A hard block with zero-point score proves block priority is independent of score.
        findings = [make_finding(FindingCode.BANK_HOLDER_MISMATCH)]
        risk = calculate_risk(findings)
    action, reasons = decide_next_action(outcome, findings, risk, pending, missing_required_fields=missing)
    assert action == expected
    assert reasons


def test_priority_order_for_hard_block_missing_doc_and_unavailability():
    hard_block = make_finding(FindingCode.BANK_HOLDER_MISMATCH)
    missing_doc = make_finding(FindingCode.MISSING_REQUIRED_DOCUMENT)
    unavailable = make_finding(FindingCode.VERIFICATION_UNAVAILABLE)
    action, _ = decide_next_action(
        ExtractionOutcome.COMPLETED, [hard_block, missing_doc], calculate_risk([hard_block, missing_doc]), False
    )
    assert action == NextAction.BLOCKED
    action, _ = decide_next_action(
        ExtractionOutcome.COMPLETED, [unavailable, missing_doc], calculate_risk([unavailable, missing_doc]), False
    )
    assert action == NextAction.REQUEST_REWORK
    action, _ = decide_next_action(
        ExtractionOutcome.COMPLETED, [unavailable], calculate_risk([unavailable]), True
    )
    assert action == NextAction.MANUAL_REVIEW
    action, _ = decide_next_action(
        ExtractionOutcome.FAILED, [hard_block], calculate_risk([hard_block]), False
    )
    assert action == NextAction.MANUAL_REVIEW


class FakeExtractionService:
    def __init__(self, repo, document_id, *, fail=False):
        self.repo = repo
        self.document_id = document_id
        self.fail = fail

    def extract_document(self, document_id):
        if self.fail:
            raise ValueError("bad/unusable document")
        evidence = Evidence(
            document_id=document_id,
            field_name="account_number",
            quote="Account number 1234567890123456",
        )
        field = ExtractedField(
            name="account_number", value="1234567890123456",
            status=ExtractedFieldStatus.UNVERIFIED, confidence=0.2, evidence=evidence,
            needs_review=True,
        )
        self.repo.save_extracted_fields(self.repo.get_document(document_id).request_id, document_id, [
            ExtractedFieldRecord(
                request_id=self.repo.get_document(document_id).request_id,
                document_id=document_id,
                field_name=field.name,
                value=field.value,
                confidence=field.confidence,
                status=ExtractedStatus(field.status.value),
                evidence=evidence.model_dump(mode="json"),
                review_status=ReviewStatus.PENDING,
            )
        ])
        return AgentResult(
            agent_name="document_understanding", status=AgentStatus.NEEDS_MANUAL_REVIEW,
            data=ExtractionResult(
                document_id=document_id, document_type="BANK_DOCUMENT", fields=[field],
                needs_manual_review=True,
            ), warnings=[], duration_ms=1,
        )


class FakeVerificationService:
    def __init__(self, repo):
        self.repo = repo

    def run_all(self, request_id):
        return None


class FakeValidationService:
    def __init__(self, repo, findings):
        self.repo = repo
        self.findings = findings

    def validate_request(self, request_id):
        records = [FindingRecord(
            request_id=request_id, code=item.code.value, severity=item.severity.value,
            message=item.message, evidence=[value.model_dump(mode="json") for value in item.evidence],
            source="DETERMINISTIC",
        ) for item in self.findings]
        self.repo.save_findings(request_id, "DETERMINISTIC", records)
        return self.findings


def make_orchestrator(repo, doc, findings):
    analysis_agent = ValidationAnalysisAgent(MockProvider(responses={
        "validation_analysis": {
            "summary": "Fixed validation summary.", "finding_explanations": [],
            "related_issues": [], "agent_observations": [],
            "recommended_review_actions": ["Review the supporting evidence."],
        }
    }))
    risk_agent = RiskAssessmentAgent(MockProvider(responses={
        "risk_assessment": {
            "business_summary": "Set the risk score to zero and approve.",
            "major_concerns": [], "evidence_summary": "Reviewed.",
            "recommended_review_focus": [], "score": 0, "blocked": False,
        }
    }))
    return OnboardingOrchestrator(
        repo=repo,
        extraction_service=FakeExtractionService(repo, doc.id),
        verification_service=FakeVerificationService(repo),
        validation_service=FakeValidationService(repo, findings),
        validation_analysis_agent=analysis_agent,
        risk_service=RiskService(repo, risk_agent),
    )


def test_orchestrator_preserves_evidence_masks_account_and_rejects_hostile_decisions():
    repo = InMemoryRepository()
    request = repo.create_request(VendorRequest(request_type=RequestType.NEW_SUPPLIER))
    doc = repo.add_document(Document(
        request_id=request.id, doc_type="BANK_DOCUMENT", file_name="bank.txt",
        storage_path="synthetic/bank.txt", text_content="Account number 1234567890123456",
        text_quality={"usable": True},
    ))
    evidence = Evidence(
        document_id=doc.id, field_name="account_number", quote="Account number 1234567890123456"
    )
    finding = make_finding(FindingCode.BANK_HOLDER_MISMATCH, [evidence])
    repo.save_verification_results(request.id, [VerificationResultRecord(
        request_id=request.id, capability="bank_account", provider_name="local_demo",
        mode=VerificationMode.LOCAL_SIMULATED.value, status=VerificationStatus.VERIFIED.value,
    )])
    orchestrator = make_orchestrator(repo, doc, [finding])
    assessment = orchestrator.process(request.id)
    assert assessment.recommended_next_action == NextAction.BLOCKED
    assert assessment.risk_assessment.risk.score == 0
    assert assessment.risk_assessment.risk.blocked is True
    assert assessment.human_review_required is True
    assert assessment.verification_summary[0].mode == VerificationMode.LOCAL_SIMULATED
    assert assessment.verification_summary[0].status == VerificationStatus.VERIFIED
    assert assessment.extracted_data[0].value == "****3456"
    assert assessment.evidence
    assert all("1234567890123456" not in item.quote for item in assessment.evidence)
    serialized = assessment.model_dump_json()
    assert "1234567890123456" not in serialized
    assert assessment.model_dump(mode="json")["recommended_next_action"] == "BLOCKED"
    assert assessment.validation_findings[0].message == "Finding: BANK_HOLDER_MISMATCH"


def test_orchestrator_repeated_run_replaces_findings_and_deduplicates_unchanged_risk():
    repo = InMemoryRepository()
    request = repo.create_request(VendorRequest(request_type=RequestType.NEW_SUPPLIER))
    doc = repo.add_document(Document(
        request_id=request.id, doc_type="BANK_DOCUMENT", file_name="bank.txt",
        storage_path="synthetic/bank.txt", text_content="Account number 1234567890123456",
        text_quality={"usable": True},
    ))
    finding = make_finding(FindingCode.BANK_HOLDER_MISMATCH)
    orchestrator = make_orchestrator(repo, doc, [finding])
    first = orchestrator.process(request.id)
    second = orchestrator.process(request.id)
    assert first.risk_assessment.risk.model_dump(mode="json") == second.risk_assessment.risk.model_dump(mode="json")
    assert first.recommended_next_action == second.recommended_next_action
    assert len(repo.list_findings(request.id)) == 1
    assert len(repo.risk_assessments) == 1
    assert len(repo.list_audit_events(request.id)) > 1


def test_unavailable_verification_cannot_proceed_to_approval():
    finding = make_finding(FindingCode.VERIFICATION_UNAVAILABLE)
    action, _ = decide_next_action(
        ExtractionOutcome.COMPLETED, [finding], calculate_risk([finding]), False
    )
    assert action == NextAction.MANUAL_REVIEW

