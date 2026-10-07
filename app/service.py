"""Stable application facade for backend consumers."""

from app.agents.document_understanding import DocumentUnderstandingAgent
from app.agents.human_review import HumanReviewAgent
from app.agents.po_draft import PODraftAgent
from app.agents.risk_assessment import RiskAssessmentAgent
from app.agents.validation_analysis import ValidationAnalysisAgent
from app.agents.vendor_draft import VendorDraftAgent
from app.config import Settings, get_settings
from app.integrations.factory import VerificationRegistry, build_verification_registry
from app.llm.factory import get_llm_provider
from app.repositories.base import OnboardingRepository
from app.repositories.factory import get_repository
from app.repositories.storage import LocalDocumentStorage, SupabaseDocumentStorage
from app.rules.config import RulesConfig
from app.schemas.assessment import AgentAssessment
from app.schemas.drafts import PODraft, VendorDraft
from app.schemas.review import HumanDecision, NextRecommendation, ReviewPackage
from app.services.draft_service import DraftService
from app.services.extraction_service import ExtractionService
from app.services.orchestration_service import OnboardingOrchestrator
from app.services.report_service import ReportService
from app.services.review_service import ReviewService
from app.services.risk_service import RiskService
from app.services.validation_service import ValidationService
from app.services.verification_service import VerificationService


class VendorOnboardingAgentService:
    """Compose existing domain services behind a stable, JSON-serializable API."""

    def __init__(self, settings: Settings | None = None, *,
                 repository: OnboardingRepository | None = None,
                 verification_registry: VerificationRegistry | None = None,
                 llm_provider=None, rules_config: RulesConfig | None = None) -> None:
        self.settings = settings or get_settings()
        self.repository = repository or get_repository(self.settings)
        provider = llm_provider or get_llm_provider(self.settings)
        rules = rules_config or RulesConfig(low_confidence_threshold=self.settings.low_confidence_threshold)
        registry = verification_registry or build_verification_registry(
            sanctions_entries=self.repository.list_sanctions_entries()
        )
        storage = (SupabaseDocumentStorage(self.settings) if self.settings.repository_backend == "supabase"
                   else LocalDocumentStorage())
        self.extraction = ExtractionService(self.repository, DocumentUnderstandingAgent(provider), storage)
        self.validation = ValidationService(self.repository, rules)
        self.verification = VerificationService(self.repository, registry)
        self.risk = RiskService(self.repository, RiskAssessmentAgent(provider), rules)
        self.orchestrator = OnboardingOrchestrator(
            self.repository, self.extraction, self.verification, self.validation,
            ValidationAnalysisAgent(provider), self.risk, rules,
        )
        self.review = ReviewService(self.repository, HumanReviewAgent(provider), rules)
        self.drafts = DraftService(
            self.repository, VendorDraftAgent(provider), PODraftAgent(provider), rules
        )
        self.reports = ReportService(self.repository)

    def process_request(self, request_id: str, force: bool = False) -> AgentAssessment:
        if self.repository.get_request(request_id) is None:
            raise KeyError(f"Request not found: {request_id}")
        existing = self.repository.list_extracted_fields(request_id)
        extract_documents = force or not existing
        return self.orchestrator.process(request_id, extract_documents=extract_documents)

    def resume_after_field_review(self, request_id: str) -> AgentAssessment:
        if self.repository.get_request(request_id) is None:
            raise KeyError(f"Request not found: {request_id}")
        if not self.repository.list_extracted_fields(request_id):
            raise ValueError("Field review cannot resume before extraction has produced fields.")
        return self.orchestrator.process(request_id, extract_documents=False)

    def get_review_package(self, request_id: str) -> ReviewPackage:
        return self.review.get_review_package(request_id)

    def submit_decision(self, request_id: str, decision: HumanDecision) -> NextRecommendation:
        return self.review.submit_decision(request_id, decision)

    def generate_drafts(self, request_id: str) -> tuple[VendorDraft, PODraft]:
        return self.drafts.generate_drafts(request_id)

    def get_report(self, request_id: str) -> dict:
        return self.reports.build_report(request_id)
