from copy import deepcopy

from app.repositories.base import OnboardingRepository
from app.schemas.domain import (
    ActorType,
    AgentRun,
    Approval,
    AuditEvent,
    Document,
    ExtractedFieldRecord,
    FindingRecord,
    PODraftRecord,
    RiskAssessmentRecord,
    SanctionsEntry,
    Vendor,
    VendorDraftRecord,
    VendorRequest,
    now_utc,
)
from app.workflow.states import assert_transition


class InMemoryRepository(OnboardingRepository):
    """Isolated in-memory implementation used by tests and local runs."""

    def __init__(
        self,
        *,
        vendors: list[Vendor] | None = None,
        sanctions_entries: list[SanctionsEntry] | None = None,
    ) -> None:
        self.requests: dict[str, VendorRequest] = {}
        self.documents: dict[str, Document] = {}
        self.extracted_fields: dict[str, ExtractedFieldRecord] = {}
        self.findings: dict[str, FindingRecord] = {}
        self.risk_assessments: dict[str, RiskAssessmentRecord] = {}
        self.approvals: dict[str, Approval] = {}
        self._audit_events: tuple[AuditEvent, ...] = ()
        self.agent_runs: dict[str, AgentRun] = {}
        self.vendors = deepcopy(vendors or [])
        self.sanctions_entries = deepcopy(sanctions_entries or [])
        self.vendor_drafts: dict[str, VendorDraftRecord] = {}
        self.po_drafts: dict[str, PODraftRecord] = {}

    def create_request(self, request: VendorRequest) -> VendorRequest:
        if request.id in self.requests:
            raise ValueError(f"Request already exists: {request.id}")
        self.requests[request.id] = deepcopy(request)
        return deepcopy(request)

    def get_request(self, request_id: str) -> VendorRequest | None:
        return deepcopy(self.requests.get(request_id))

    def list_requests(self) -> list[VendorRequest]:
        return deepcopy(list(self.requests.values()))

    def set_request_status(
        self, request_id: str, new_status: str, actor: str, reason: str
    ) -> VendorRequest:
        current = self._required(self.requests, request_id, "request")
        assert_transition(current.status, new_status)
        before = current.status
        updated = current.model_copy(update={"status": new_status, "updated_at": now_utc()})
        self.requests[request_id] = updated
        self.append_audit_event(
            AuditEvent(
                request_id=request_id,
                actor=actor,
                actor_type=ActorType.SYSTEM,
                event_type="REQUEST_STATUS_CHANGED",
                details={"from": before, "to": new_status, "reason": reason},
            )
        )
        return deepcopy(updated)

    def add_document(self, document: Document) -> Document:
        self._required(self.requests, document.request_id, "request")
        self.documents[document.id] = deepcopy(document)
        return deepcopy(document)

    def get_document(self, document_id: str) -> Document | None:
        return deepcopy(self.documents.get(document_id))

    def update_document_text(
        self, document_id: str, text_content: str, text_quality: dict
    ) -> Document:
        current = self._required(self.documents, document_id, "document")
        updated = current.model_copy(
            update={"text_content": text_content, "text_quality": deepcopy(text_quality)}
        )
        self.documents[document_id] = updated
        return deepcopy(updated)

    def list_documents(self, request_id: str) -> list[Document]:
        return self._for_request(self.documents, request_id)

    def save_extracted_fields(
        self, request_id: str, document_id: str, fields: list[ExtractedFieldRecord]
    ) -> list[ExtractedFieldRecord]:
        self._required(self.requests, request_id, "request")
        existing = [
            item.id
            for item in self.extracted_fields.values()
            if item.request_id == request_id and item.document_id == document_id
        ]
        for field_id in existing:
            del self.extracted_fields[field_id]
        for item in fields:
            if item.request_id != request_id or item.document_id != document_id:
                raise ValueError("Extracted field request_id/document_id do not match save scope")
            self.extracted_fields[item.id] = deepcopy(item)
        return deepcopy(fields)

    def list_extracted_fields(self, request_id: str) -> list[ExtractedFieldRecord]:
        return self._for_request(self.extracted_fields, request_id)

    def save_findings(
        self, request_id: str, source: str, findings: list[FindingRecord]
    ) -> list[FindingRecord]:
        self._required(self.requests, request_id, "request")
        existing = [
            item.id
            for item in self.findings.values()
            if item.request_id == request_id and item.source == source
        ]
        for finding_id in existing:
            del self.findings[finding_id]
        for item in findings:
            if item.request_id != request_id or item.source != source:
                raise ValueError("Finding request_id/source do not match save scope")
            self.findings[item.id] = deepcopy(item)
        return deepcopy(findings)

    def list_findings(self, request_id: str) -> list[FindingRecord]:
        return self._for_request(self.findings, request_id)

    def save_risk_assessment(self, assessment: RiskAssessmentRecord) -> RiskAssessmentRecord:
        self._required(self.requests, assessment.request_id, "request")
        self.risk_assessments[assessment.id] = deepcopy(assessment)
        return deepcopy(assessment)

    def get_latest_risk_assessment(self, request_id: str) -> RiskAssessmentRecord | None:
        return self._latest(self.risk_assessments, request_id)

    def add_approval(self, approval: Approval) -> Approval:
        self._required(self.requests, approval.request_id, "request")
        self.approvals[approval.id] = deepcopy(approval)
        return deepcopy(approval)

    def list_approvals(self, request_id: str) -> list[Approval]:
        return self._for_request(self.approvals, request_id)

    def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        if event.request_id is not None:
            self._required(self.requests, event.request_id, "request")
        self._audit_events += (deepcopy(event),)
        return deepcopy(event)

    def list_audit_events(self, request_id: str | None = None) -> list[AuditEvent]:
        events = self._audit_events
        if request_id is not None:
            events = [event for event in events if event.request_id == request_id]
        return deepcopy(events)

    def list_vendors(self) -> list[Vendor]:
        return deepcopy(self.vendors)

    def list_sanctions_entries(self) -> list[SanctionsEntry]:
        return deepcopy(self.sanctions_entries)

    def save_agent_run(self, run: AgentRun) -> AgentRun:
        self._required(self.requests, run.request_id, "request")
        self.agent_runs[run.id] = deepcopy(run)
        return deepcopy(run)

    def save_vendor_draft(self, draft: VendorDraftRecord) -> VendorDraftRecord:
        self._required(self.requests, draft.request_id, "request")
        self.vendor_drafts[draft.request_id] = deepcopy(draft)
        return deepcopy(draft)

    def get_vendor_draft(self, request_id: str) -> VendorDraftRecord | None:
        return deepcopy(self.vendor_drafts.get(request_id))

    def save_po_draft(self, draft: PODraftRecord) -> PODraftRecord:
        self._required(self.requests, draft.request_id, "request")
        self.po_drafts[draft.request_id] = deepcopy(draft)
        return deepcopy(draft)

    def get_po_draft(self, request_id: str) -> PODraftRecord | None:
        return deepcopy(self.po_drafts.get(request_id))

    @staticmethod
    def _required(collection: dict, key: str, label: str):
        try:
            return collection[key]
        except KeyError as exc:
            raise KeyError(f"{label.capitalize()} not found: {key}") from exc

    @staticmethod
    def _for_request(collection: dict, request_id: str) -> list:
        return deepcopy([item for item in collection.values() if item.request_id == request_id])

    @staticmethod
    def _latest(collection: dict, request_id: str):
        matches = [item for item in collection.values() if item.request_id == request_id]
        return deepcopy(max(matches, key=lambda item: item.created_at)) if matches else None
