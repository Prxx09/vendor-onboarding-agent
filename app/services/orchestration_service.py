import json
import re
from uuid import NAMESPACE_URL, uuid5

from app.agents.validation_analysis import ValidationAnalysisAgent
from app.orchestration.decision import decide_next_action
from app.repositories.base import OnboardingRepository
from app.rules.config import RulesConfig
from app.rules.document_fields import DocumentType
from app.schemas.assessment import (
    AgentAssessment,
    AssessedExtractedField,
    ExtractionOutcome,
    VerificationSummary,
)
from app.schemas.common import AgentStatus, Evidence
from app.schemas.domain import (
    ActorType,
    AuditEvent,
    ExtractedFieldRecord,
    FindingRecord,
    ReviewStatus,
)
from app.schemas.findings import Finding
from app.schemas.validation_analysis import (
    ExtractedSummaryField,
    ValidationAnalysisInput,
    ValidationAnalysisResult,
    ValidationRequestSummary,
)
from app.services.extraction_service import ExtractionService
from app.services.risk_service import RiskService
from app.services.validation_service import ValidationService
from app.services.verification_service import VerificationService
from app.tools.pdf_text import assess_text_quality
from app.utils.masking import mask_account_number
from app.workflow.states import WorkflowStatus


class OnboardingOrchestrator:
    """Coordinate existing Phase 0–4 services without delegating decisions to an LLM."""

    def __init__(
        self,
        repo: OnboardingRepository,
        extraction_service: ExtractionService,
        verification_service: VerificationService,
        validation_service: ValidationService,
        validation_analysis_agent: ValidationAnalysisAgent,
        risk_service: RiskService,
        rules_config: RulesConfig | None = None,
    ) -> None:
        self.repo = repo
        self.extraction_service = extraction_service
        self.verification_service = verification_service
        self.validation_service = validation_service
        self.validation_analysis_agent = validation_analysis_agent
        self.risk_service = risk_service
        self.rules_config = rules_config or RulesConfig()

    def process(self, request_id: str, *, extract_documents: bool = True) -> AgentAssessment:
        request = self.repo.get_request(request_id)
        if request is None:
            raise KeyError(f"Request not found: {request_id}")

        documents = self.repo.list_documents(request_id)
        warnings: list[str] = []
        failed = False
        unusable = False
        missing_required_fields: set[str] = set()
        for document in (documents if extract_documents else []):
            try:
                result = self.extraction_service.extract_document(document.id)
            except Exception as exc:  # noqa: BLE001 - contain per-document processing failures
                failed = True
                warnings.append(
                    f"Extraction failed for document {document.id} ({type(exc).__name__})."
                )
                continue
            warnings.extend(result.warnings)
            if result.status == AgentStatus.NEEDS_MANUAL_REVIEW and result.data is None:
                failed = True
            if result.data is None:
                failed = True
            else:
                missing_required_fields.update(result.data.missing_required_fields)
            updated_document = self.repo.get_document(document.id)
            quality = (updated_document.text_quality or {}) if updated_document else {}
            if "usable" in quality:
                unusable |= not bool(quality["usable"])
            elif updated_document and updated_document.text_content:
                unusable |= not assess_text_quality(updated_document.text_content).usable

        if not extract_documents:
            extracted_records = self.repo.list_extracted_fields(request_id)
            extraction_status = ExtractionOutcome.COMPLETED if extracted_records else (
                ExtractionOutcome.NOT_RUN if not documents else ExtractionOutcome.FAILED
            )
            unusable = any(
                (document.text_quality or {}).get("usable") is False for document in documents
            )
        extraction_status = (
            ExtractionOutcome.UNUSABLE if unusable else extraction_status
        ) if not extract_documents else (
            ExtractionOutcome.FAILED if failed else
            ExtractionOutcome.UNUSABLE if unusable else
            ExtractionOutcome.COMPLETED if documents else
            ExtractionOutcome.NOT_RUN
        )

        # The service persists fresh provider results and converts any provider error into
        # UNAVAILABLE; downstream validation consumes those persisted results.
        self.verification_service.run_all(request_id)
        findings = self.validation_service.validate_request(request_id)
        findings = self._stabilize_finding_ids(request_id, findings)
        extracted_records = self.repo.list_extracted_fields(request_id)
        document_types = self._document_types(request_id)
        extracted_summaries = self._analysis_fields(extracted_records, document_types)
        validation_agent_result = self.validation_analysis_agent.run(
            ValidationAnalysisInput(
                request_summary=ValidationRequestSummary(
                    request_id=request.id,
                    request_type=request.request_type.value,
                    supplier_name=request.supplier_name,
                    legal_name=request.legal_name,
                    country=request.country,
                    estimated_annual_spend=(
                        str(request.estimated_annual_spend)
                        if request.estimated_annual_spend is not None else None
                    ),
                ),
                extracted_summary=extracted_summaries,
                findings=findings,
            )
        )
        if validation_agent_result.data is None:
            # Existing ValidationAnalysisAgent normally returns a deterministic fallback.
            validation_analysis = ValidationAnalysisResult(
                summary="Validation analysis could not be generated; deterministic findings are retained."
            )
            warnings.append("Validation analysis agent returned no data; using a fixed summary.")
        else:
            validation_analysis = validation_agent_result.data
        warnings.extend(validation_agent_result.warnings)

        risk_assessment = self.risk_service.assess(
            request_id, validation_analysis_summary=validation_analysis.summary
        )
        if risk_assessment.explanation_status.value == "TEMPLATE_FALLBACK":
            warnings.append("Risk explanation used the deterministic template fallback.")
        warnings = [_mask_labeled_account_text(item) for item in warnings]
        pending_review = any(
            record.review_status == ReviewStatus.PENDING
            and (
                record.status.value == "UNVERIFIED"
                or record.confidence is None
                or float(record.confidence) < self.rules_config.low_confidence_threshold
            )
            for record in extracted_records
        )
        action, reasons = decide_next_action(
            extraction_status,
            findings,
            risk_assessment.risk,
            pending_review,
            missing_required_fields=missing_required_fields,
        )
        safe_extracted = [
            self._safe_field(record, document_types.get(record.document_id, DocumentType.UNKNOWN))
            for record in extracted_records
        ]
        safe_findings = [self._safe_finding(item) for item in findings]
        evidence = self._collect_evidence(safe_extracted, safe_findings)
        verification_summary = [
            VerificationSummary(
                capability=record.capability,
                provider_name=record.provider_name,
                mode=record.mode,
                status=record.status,
            )
            for record in self.repo.list_verification_results(request_id)
        ]
        explanation = " ".join(
            part.strip()
            for part in (
                validation_analysis.summary,
                risk_assessment.explanation.business_summary,
            )
            if part and part.strip()
        )
        assessment = AgentAssessment(
            request_id=request_id,
            extraction_status=extraction_status,
            extracted_data=safe_extracted,
            validation_findings=safe_findings,
            validation_analysis=validation_analysis,
            risk_assessment=risk_assessment,
            verification_summary=verification_summary,
            evidence=evidence,
            recommended_next_action=action,
            human_review_required=True,
            reasons=reasons,
            explanation=explanation,
            warnings=warnings,
        )
        self._sync_workflow_status(request_id, action, pending_review)
        self.repo.append_audit_event(
            AuditEvent(
                request_id=request_id,
                actor="onboarding_orchestrator",
                actor_type=ActorType.SYSTEM,
                event_type="ONBOARDING_ASSESSMENT_COMPLETED",
                details={
                    "recommended_next_action": action.value,
                    "extraction_status": extraction_status.value,
                    "finding_count": len(findings),
                    "risk_score": risk_assessment.risk.score,
                    "risk_label": risk_assessment.risk.label.value,
                    "blocked": risk_assessment.risk.blocked,
                    "human_review_required": True,
                },
            )
        )
        return assessment

    def _sync_workflow_status(self, request_id: str, action, pending_review: bool) -> None:
        """Persist deterministic routing for intake states; leave approval states alone."""
        request = self.repo.get_request(request_id)
        if request is None:
            return
        status = WorkflowStatus(request.status)
        managed = {
            WorkflowStatus.DRAFT, WorkflowStatus.DOCUMENTS_UPLOADED,
            WorkflowStatus.EXTRACTED, WorkflowStatus.PENDING_FIELD_REVIEW,
            WorkflowStatus.VALIDATED, WorkflowStatus.NEEDS_MANUAL_REVIEW,
        }
        if status not in managed:
            return
        target = {
            "MANUAL_REVIEW": WorkflowStatus.NEEDS_MANUAL_REVIEW,
            "BLOCKED": WorkflowStatus.BLOCKED,
            "REQUEST_REWORK": WorkflowStatus.REWORK,
        }.get(action.value)
        if target is None:
            target = WorkflowStatus.PENDING_FIELD_REVIEW if pending_review else WorkflowStatus.PENDING_PROCUREMENT
        # Walk only legal deterministic intake transitions. No policy decisions are made here.
        route = {
            WorkflowStatus.DRAFT: [WorkflowStatus.DOCUMENTS_UPLOADED, WorkflowStatus.EXTRACTED],
            WorkflowStatus.DOCUMENTS_UPLOADED: [WorkflowStatus.EXTRACTED],
            WorkflowStatus.NEEDS_MANUAL_REVIEW: [WorkflowStatus.EXTRACTED],
            WorkflowStatus.EXTRACTED: [],
            WorkflowStatus.PENDING_FIELD_REVIEW: [],
            WorkflowStatus.VALIDATED: [],
        }[status]
        for step in route:
            self.repo.set_request_status(request_id, step, "onboarding_orchestrator", "Deterministic intake processing.")
            status = step
        if status in {WorkflowStatus.EXTRACTED, WorkflowStatus.PENDING_FIELD_REVIEW} and target in {
            WorkflowStatus.PENDING_PROCUREMENT, WorkflowStatus.REWORK, WorkflowStatus.BLOCKED
        }:
            self.repo.set_request_status(request_id, WorkflowStatus.VALIDATED, "onboarding_orchestrator", "Deterministic checks completed.")
            status = WorkflowStatus.VALIDATED
        if status == WorkflowStatus.PENDING_FIELD_REVIEW and target == WorkflowStatus.PENDING_PROCUREMENT:
            self.repo.set_request_status(request_id, WorkflowStatus.VALIDATED, "onboarding_orchestrator", "Field review completed.")
            status = WorkflowStatus.VALIDATED
        if status == target:
            return
        from app.workflow.states import can_transition
        if can_transition(status, target):
            self.repo.set_request_status(request_id, target, "onboarding_orchestrator", "Deterministic onboarding recommendation.")

    def _document_types(self, request_id: str) -> dict[str, DocumentType]:
        result = {}
        for document in self.repo.list_documents(request_id):
            try:
                result[document.id] = DocumentType(document.doc_type.upper())
            except ValueError:
                result[document.id] = DocumentType.UNKNOWN
        return result

    def _stabilize_finding_ids(self, request_id: str, findings: list[Finding]) -> list[Finding]:
        """Keep regenerated deterministic finding references stable across pipeline runs."""
        stable = []
        for finding in findings:
            identity = {
                "request_id": request_id,
                "code": finding.code.value,
                "severity": finding.severity.value,
                "message": finding.message,
                "evidence": [item.model_dump(mode="json") for item in finding.evidence],
                "source": finding.source,
                "related_vendor_id": finding.related_vendor_id,
            }
            stable_id = str(uuid5(NAMESPACE_URL, json.dumps(identity, sort_keys=True)))
            stable.append(finding.model_copy(update={"id": stable_id}))
        by_source: dict[str, list] = {}
        for finding in stable:
            by_source.setdefault(finding.source, []).append(finding)
        for source, source_findings in by_source.items():
            self.repo.save_findings(
                request_id,
                source,
                [
                    FindingRecord(
                        request_id=request_id,
                        id=finding.id,
                        code=finding.code.value,
                        severity=finding.severity.value,
                        message=finding.message,
                        evidence=[item.model_dump(mode="json") for item in finding.evidence],
                        source=source,
                    )
                    for finding in source_findings
                ],
            )
        return stable

    @staticmethod
    def _analysis_fields(
        records: list[ExtractedFieldRecord], document_types: dict[str, DocumentType]
    ) -> list[ExtractedSummaryField]:
        result: list[ExtractedSummaryField] = []
        for record in records:
            field_value = record.value
            if "account" in record.field_name.casefold() or "iban" in record.field_name.casefold():
                field_value = mask_account_number(str(field_value)) if field_value is not None else None
            evidence_refs = []
            for item in _evidence_dicts(record.evidence):
                evidence_refs.append(f"{item.get('document_id', record.document_id)}:{item.get('field_name', record.field_name)}")
            result.append(ExtractedSummaryField(
                document_type=document_types.get(record.document_id, DocumentType.UNKNOWN).value,
                field_name=record.field_name,
                value=field_value,
                confidence=float(record.confidence) if record.confidence is not None else None,
                evidence_refs=evidence_refs,
            ))
        return result

    @staticmethod
    def _safe_field(
        record: ExtractedFieldRecord, document_type: DocumentType
    ) -> AssessedExtractedField:
        value = record.value
        if "account" in record.field_name.casefold() or "iban" in record.field_name.casefold():
            value = mask_account_number(str(value)) if value is not None else None
        evidence = []
        for item in _evidence_dicts(record.evidence):
            quote = _mask_labeled_account_text(str(item.get("quote", "")))
            evidence.append(Evidence.model_validate({**item, "quote": quote}))
        return AssessedExtractedField(
            document_id=record.document_id,
            document_type=document_type,
            field_name=record.field_name,
            value=value,
            confidence=float(record.confidence) if record.confidence is not None else None,
            status=record.status,
            review_status=record.review_status,
            evidence=evidence,
        )

    @staticmethod
    def _safe_finding(finding: Finding) -> Finding:
        return finding.model_copy(
            update={
                "message": _mask_labeled_account_text(finding.message),
                "evidence": [
                    evidence.model_copy(
                        update={"quote": _mask_labeled_account_text(evidence.quote)}
                    )
                    for evidence in finding.evidence
                ],
            }
        )

    @staticmethod
    def _collect_evidence(
        fields: list[AssessedExtractedField], findings: list[Finding]
    ) -> list[Evidence]:
        unique: dict[tuple[str, str, str, int | None, str | None], Evidence] = {}
        for item in [evidence for field in fields for evidence in field.evidence] + [
            evidence for finding in findings for evidence in finding.evidence
        ]:
            key = (item.document_id, item.field_name, item.quote, item.page, item.verification_mode)
            unique[key] = item
        return [unique[key] for key in sorted(unique, key=lambda value: tuple(str(part) for part in value))]


def _evidence_dicts(value: dict | list | None) -> list[dict]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _mask_labeled_account_text(value: str) -> str:
    if re.search(
        r"(?i)\b(?:account\s*(?:number|no\.?|#)|a/c\s*(?:number|no\.?|#)|iban)\s*[:#-]?",
        value,
    ):
        return mask_account_number(value) or ""
    return value
