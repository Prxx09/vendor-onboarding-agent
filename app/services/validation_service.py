from datetime import UTC, date, datetime

from app.repositories.base import OnboardingRepository
from app.rules.config import RulesConfig
from app.rules.document_fields import DocumentType
from app.rules.validation.context import ValidationContext
from app.rules.validation.registry import run_validations
from app.schemas.domain import ActorType, AuditEvent, FindingRecord
from app.schemas.findings import Finding


class ValidationService:
    def __init__(self, repo: OnboardingRepository, rules_config: RulesConfig | None = None) -> None:
        self.repo = repo
        self.rules_config = rules_config or RulesConfig()

    def validate_request(self, request_id: str, *, today: date | None = None) -> list[Finding]:
        request = self.repo.get_request(request_id)
        if request is None:
            raise KeyError(f"Request not found: {request_id}")
        documents = self.repo.list_documents(request_id)
        document_types = {document.id: self._document_type(document.doc_type) for document in documents}
        grouped: dict[DocumentType, list] = {}
        for field in self.repo.list_extracted_fields(request_id):
            document_type = document_types.get(field.document_id, DocumentType.UNKNOWN)
            grouped.setdefault(document_type, []).append(field)
        context = ValidationContext(
            request=request,
            documents=documents,
            extracted_fields=grouped,
            existing_vendors=self.repo.list_vendors(),
            sanctions_entries=self.repo.list_sanctions_entries(),
            rules_config=self.rules_config,
            today=today or datetime.now(UTC).date(),
        )
        findings = run_validations(context)
        persisted = [
            FindingRecord(
                id=item.id,
                request_id=request_id,
                code=item.code.value,
                severity=item.severity.value,
                message=item.message,
                evidence=[evidence.model_dump(mode="json") for evidence in item.evidence],
                source="DETERMINISTIC",
            )
            for item in findings
        ]
        self.repo.save_findings(request_id, "DETERMINISTIC", persisted)
        self.repo.append_audit_event(
            AuditEvent(
                request_id=request_id,
                actor="validation_service",
                actor_type=ActorType.SYSTEM,
                event_type="VALIDATION_COMPLETED",
                details={
                    "finding_count": len(findings),
                    "finding_codes": [item.code.value for item in findings],
                },
            )
        )
        return findings

    @staticmethod
    def _document_type(value: str) -> DocumentType:
        try:
            return DocumentType(value.upper())
        except ValueError:
            return DocumentType.UNKNOWN
