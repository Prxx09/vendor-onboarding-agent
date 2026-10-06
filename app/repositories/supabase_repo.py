from typing import Any, TypeVar

from app.config import Settings
from app.repositories.base import OnboardingRepository
from app.schemas.domain import (
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
from supabase import Client, create_client

M = TypeVar("M")


class SupabaseRepository(OnboardingRepository):
    def __init__(self, settings: Settings, client: Client | None = None) -> None:
        if client is None and (not settings.supabase_url or not settings.supabase_service_key):
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY are required when "
                "REPOSITORY_BACKEND=supabase"
            )
        self.client = client or create_client(settings.supabase_url, settings.supabase_service_key)

    def create_request(self, request: VendorRequest) -> VendorRequest:
        return self._insert("vendor_requests", request, VendorRequest)

    def get_request(self, request_id: str) -> VendorRequest | None:
        return self._one("vendor_requests", VendorRequest, "id", request_id)

    def list_requests(self) -> list[VendorRequest]:
        return self._list("vendor_requests", VendorRequest)

    def set_request_status(
        self, request_id: str, new_status: str, actor: str, reason: str
    ) -> VendorRequest:
        current = self.get_request(request_id)
        if current is None:
            raise KeyError(f"Request not found: {request_id}")
        assert_transition(current.status, new_status)
        response = (
            self.client.table("vendor_requests")
            .update({"status": str(new_status), "updated_at": now_utc().isoformat()})
            .eq("id", request_id)
            .select("*")
            .execute()
        )
        updated = self._parse_one(response.data, VendorRequest)
        self.append_audit_event(
            AuditEvent(
                request_id=request_id,
                actor=actor,
                actor_type="SYSTEM",
                event_type="REQUEST_STATUS_CHANGED",
                details={"from": current.status, "to": str(new_status), "reason": reason},
            )
        )
        return updated

    def add_document(self, document: Document) -> Document:
        return self._insert("documents", document, Document)

    def get_document(self, document_id: str) -> Document | None:
        return self._one("documents", Document, "id", document_id)

    def list_documents(self, request_id: str) -> list[Document]:
        return self._list("documents", Document, request_id)

    def update_document_text(
        self, document_id: str, text_content: str, text_quality: dict
    ) -> Document:
        response = (
            self.client.table("documents")
            .update({"text_content": text_content, "text_quality": text_quality})
            .eq("id", document_id)
            .select("*")
            .execute()
        )
        return self._parse_one(response.data, Document)

    def save_extracted_fields(
        self, request_id: str, document_id: str, fields: list[ExtractedFieldRecord]
    ) -> list[ExtractedFieldRecord]:
        for item in fields:
            if item.request_id != request_id or item.document_id != document_id:
                raise ValueError("Extracted field request_id/document_id do not match save scope")
        self.client.table("extracted_fields").delete().eq("request_id", request_id).eq(
            "document_id", document_id
        ).execute()
        return self._insert_many("extracted_fields", fields, ExtractedFieldRecord)

    def list_extracted_fields(self, request_id: str) -> list[ExtractedFieldRecord]:
        return self._list("extracted_fields", ExtractedFieldRecord, request_id)

    def save_findings(
        self, request_id: str, source: str, findings: list[FindingRecord]
    ) -> list[FindingRecord]:
        if any(item.request_id != request_id or item.source != source for item in findings):
            raise ValueError("Finding request_id/source do not match save scope")
        self.client.table("validation_findings").delete().eq("request_id", request_id).eq(
            "source", source
        ).execute()
        return self._insert_many("validation_findings", findings, FindingRecord)

    def list_findings(self, request_id: str) -> list[FindingRecord]:
        return self._list("validation_findings", FindingRecord, request_id)

    def save_risk_assessment(self, assessment: RiskAssessmentRecord) -> RiskAssessmentRecord:
        return self._insert("risk_assessments", assessment, RiskAssessmentRecord)

    def get_latest_risk_assessment(self, request_id: str) -> RiskAssessmentRecord | None:
        response = (
            self.client.table("risk_assessments")
            .select("*")
            .eq("request_id", request_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return self._parse_optional(response.data, RiskAssessmentRecord)

    def add_approval(self, approval: Approval) -> Approval:
        return self._insert("approvals", approval, Approval)

    def list_approvals(self, request_id: str) -> list[Approval]:
        return self._list("approvals", Approval, request_id)

    def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        return self._insert("audit_events", event, AuditEvent)

    def list_audit_events(self, request_id: str | None = None) -> list[AuditEvent]:
        query = self.client.table("audit_events").select("*")
        if request_id is not None:
            query = query.eq("request_id", request_id)
        return [AuditEvent.model_validate(row) for row in query.order("created_at").execute().data]

    def list_vendors(self) -> list[Vendor]:
        return self._list("vendors", Vendor)

    def list_sanctions_entries(self) -> list[SanctionsEntry]:
        return self._list("sanctions_entries", SanctionsEntry)

    def save_agent_run(self, run: AgentRun) -> AgentRun:
        return self._insert("agent_runs", run, AgentRun)

    def save_vendor_draft(self, draft: VendorDraftRecord) -> VendorDraftRecord:
        return self._upsert("vendor_drafts", draft, VendorDraftRecord, "request_id")

    def get_vendor_draft(self, request_id: str) -> VendorDraftRecord | None:
        return self._one("vendor_drafts", VendorDraftRecord, "request_id", request_id)

    def save_po_draft(self, draft: PODraftRecord) -> PODraftRecord:
        return self._upsert("po_drafts", draft, PODraftRecord, "request_id")

    def get_po_draft(self, request_id: str) -> PODraftRecord | None:
        return self._one("po_drafts", PODraftRecord, "request_id", request_id)

    def _insert(self, table: str, model: M, model_type: type[M]) -> M:
        response = self.client.table(table).insert(self._dump(model)).select("*").execute()
        return self._parse_one(response.data, model_type)

    def _insert_many(self, table: str, models: list[M], model_type: type[M]) -> list[M]:
        if not models:
            return []
        response = (
            self.client.table(table)
            .insert([self._dump(model) for model in models])
            .select("*")
            .execute()
        )
        return [model_type.model_validate(row) for row in response.data]

    def _upsert(self, table: str, model: M, model_type: type[M], conflict: str) -> M:
        response = (
            self.client.table(table)
            .upsert(self._dump(model), on_conflict=conflict)
            .select("*")
            .execute()
        )
        return self._parse_one(response.data, model_type)

    def _one(self, table: str, model_type: type[M], column: str, value: str) -> M | None:
        response = self.client.table(table).select("*").eq(column, value).limit(1).execute()
        return self._parse_optional(response.data, model_type)

    def _list(self, table: str, model_type: type[M], request_id: str | None = None) -> list[M]:
        query = self.client.table(table).select("*")
        if request_id is not None:
            query = query.eq("request_id", request_id)
        return [model_type.model_validate(row) for row in query.execute().data]

    @staticmethod
    def _dump(model: Any) -> dict[str, Any]:
        return model.model_dump(mode="json")

    @staticmethod
    def _parse_one(rows: list[dict[str, Any]], model_type: type[M]) -> M:
        if not rows:
            raise RuntimeError(f"Supabase returned no row for {model_type.__name__}")
        return model_type.model_validate(rows[0])

    @classmethod
    def _parse_optional(cls, rows: list[dict[str, Any]], model_type: type[M]) -> M | None:
        return cls._parse_one(rows, model_type) if rows else None
