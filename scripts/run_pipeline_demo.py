"""Offline Phase 5 pipeline examples using InMemoryRepository and MockProvider."""

from app.agents.risk_assessment import RiskAssessmentAgent
from app.agents.validation_analysis import ValidationAnalysisAgent
from app.integrations.base import VerificationMode, VerificationStatus
from app.llm.mock_provider import MockProvider
from app.repositories.memory import InMemoryRepository
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
from app.schemas.extraction import ExtractionResult
from app.schemas.findings import Finding, FindingCode, FindingSeverity
from app.services.orchestration_service import OnboardingOrchestrator
from app.services.risk_service import RiskService


class DemoExtractionService:
    def __init__(self, repo, *, fail=False, low_confidence=False):
        self.repo = repo
        self.fail = fail
        self.low_confidence = low_confidence

    def extract_document(self, document_id):
        if self.fail:
            raise ValueError("synthetic extraction failure")
        document = self.repo.get_document(document_id)
        if self.low_confidence:
            self.repo.save_extracted_fields(document.request_id, document_id, [
                ExtractedFieldRecord(
                    request_id=document.request_id,
                    document_id=document_id,
                    field_name="legal_name",
                    value="Example Supplier",
                    confidence=0.4,
                    status=ExtractedStatus.UNVERIFIED,
                    evidence={
                        "document_id": document_id,
                        "field_name": "legal_name",
                        "quote": "Legal name: Example Supplier",
                    },
                    review_status=ReviewStatus.PENDING,
                )
            ])
        return AgentResult(
            agent_name="document_understanding",
            status=AgentStatus.OK,
            data=ExtractionResult(
                document_id=document_id,
                document_type="BUSINESS_REGISTRATION",
                fields=[],
                needs_manual_review=False,
            ),
            duration_ms=0,
        )


class DemoVerificationService:
    def __init__(self, repo, status):
        self.repo = repo
        self.status = status

    def run_all(self, request_id):
        self.repo.save_verification_results(request_id, [
            VerificationResultRecord(
                request_id=request_id,
                capability="company_registry",
                provider_name="offline_demo_provider",
                mode=VerificationMode.LOCAL_SIMULATED.value,
                status=self.status.value,
            )
        ])


class DemoValidationService:
    def __init__(self, repo, codes):
        self.repo = repo
        self.codes = codes

    def validate_request(self, request_id):
        findings = [Finding(
            code=code,
            severity=(FindingSeverity.BLOCKING if code in {
                FindingCode.SANCTIONS_MATCH,
                FindingCode.MISSING_REQUIRED_DOCUMENT,
                FindingCode.VERIFICATION_UNAVAILABLE,
            } else FindingSeverity.WARNING),
            message=f"Synthetic demo finding: {code.value}",
            evidence=[Evidence(
                document_id="verification:company_registry",
                field_name="status",
                quote=self._status_quote(code),
                verification_mode=VerificationMode.LOCAL_SIMULATED.value,
            )] if code == FindingCode.VERIFICATION_UNAVAILABLE else [],
        ) for code in self.codes]
        records = [FindingRecord(
            request_id=request_id,
            code=item.code.value,
            severity=item.severity.value,
            message=item.message,
            evidence=[value.model_dump(mode="json") for value in item.evidence],
            source="DETERMINISTIC",
        ) for item in findings]
        self.repo.save_findings(request_id, "DETERMINISTIC", records)
        return findings

    def _status_quote(self, code):
        return "UNAVAILABLE" if code == FindingCode.VERIFICATION_UNAVAILABLE else code.value


def make_case(label, codes=(), *, verification=VerificationStatus.VERIFIED,
              extraction_failure=False, low_confidence=False):
    repo = InMemoryRepository()
    request = repo.create_request(VendorRequest(
        request_type=RequestType.NEW_SUPPLIER,
        supplier_name="Synthetic Example Supplier",
        is_demo=True,
    ))
    repo.add_document(Document(
        request_id=request.id,
        doc_type="BUSINESS_REGISTRATION",
        file_name="synthetic-business-registration.txt",
        storage_path=f"synthetic/{request.id}/registration.txt",
        text_content="Synthetic registration document for offline demonstration.",
        text_quality={"usable": not extraction_failure},
    ))
    agent_response = {
        "business_summary": "This is an offline example for human review.",
        "major_concerns": [],
        "evidence_summary": "All verification behavior is simulated.",
        "recommended_review_focus": ["Review the source records."],
    }
    orchestrator = OnboardingOrchestrator(
        repo=repo,
        extraction_service=DemoExtractionService(
            repo, fail=extraction_failure, low_confidence=low_confidence
        ),
        verification_service=DemoVerificationService(repo, verification),
        validation_service=DemoValidationService(repo, list(codes)),
        validation_analysis_agent=ValidationAnalysisAgent(MockProvider(responses={
            "validation_analysis": {
                "summary": "Synthetic deterministic validation summary.",
                "finding_explanations": [], "related_issues": [],
                "agent_observations": [], "recommended_review_actions": [],
            }
        })),
        risk_service=RiskService(
            repo,
            RiskAssessmentAgent(MockProvider(responses={"risk_assessment": agent_response})),
        ),
    )
    assessment = orchestrator.process(request.id)
    print(f"\n{label}")
    print(f"  request_id: {assessment.request_id}")
    print(f"  extraction_outcome: {assessment.extraction_status.value}")
    print("  verification_summary:")
    for item in assessment.verification_summary:
        print(f"    {item.capability}: {item.provider_name}, {item.mode.value}, {item.status.value}")
    print(f"  validation_findings: {[item.code.value for item in assessment.validation_findings]}")
    print(f"  risk: {assessment.risk_assessment.risk.score} / {assessment.risk_assessment.risk.label.value}")
    print(f"  hard_blocks: {[item.value for item in assessment.risk_assessment.risk.hard_blocks]}")
    print(f"  recommended_next_action: {assessment.recommended_next_action.value}")
    print(f"  reasons: {assessment.reasons}")
    print(f"  human_review_required: {assessment.human_review_required}")


def main():
    make_case("clean supplier")
    make_case("missing required document", [FindingCode.MISSING_REQUIRED_DOCUMENT])
    make_case("hard-block case", [FindingCode.SANCTIONS_MATCH])
    make_case(
        "verification unavailable", [FindingCode.VERIFICATION_UNAVAILABLE],
        verification=VerificationStatus.UNAVAILABLE,
    )
    make_case(
        "low-confidence/manual-review case", [FindingCode.LOW_CONFIDENCE_FIELD],
        low_confidence=True,
    )
    make_case("extraction failure/manual-review case", extraction_failure=True)


if __name__ == "__main__":
    main()
