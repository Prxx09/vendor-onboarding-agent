from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.repositories.factory import get_repository
from app.repositories.memory import InMemoryRepository
from app.repositories.storage import LocalDocumentStorage
from app.schemas.domain import (
    ActorType,
    AgentRun,
    Approval,
    ApprovalDecision,
    ApprovalStage,
    AuditEvent,
    Document,
    ExtractedFieldRecord,
    ExtractedStatus,
    FindingRecord,
    PODraftRecord,
    RequestType,
    ReviewStatus,
    RiskAssessmentRecord,
    Vendor,
    VendorDraftRecord,
    VendorRequest,
    VerificationResultRecord,
)
from app.workflow.states import WorkflowStatus, assert_transition, can_transition


def test_workflow_transitions():
    assert can_transition(WorkflowStatus.DRAFT, WorkflowStatus.DOCUMENTS_UPLOADED)
    assert can_transition("PENDING_BUDGET", "APPROVED")
    assert not can_transition("REJECTED", "DRAFT")
    assert not can_transition("unknown", "DRAFT")
    with pytest.raises(ValueError, match="Invalid workflow transition"):
        assert_transition("DRAFT", "APPROVED")


def test_factory_rejects_missing_supabase_credentials():
    settings = Settings(
        repository_backend="supabase",
        supabase_url=None,
        supabase_service_key=None,
        _env_file=None,
    )
    with pytest.raises(ValueError, match="SUPABASE_URL and SUPABASE_SERVICE_KEY"):
        get_repository(settings)


def test_repository_status_change_audits(repository, contract_request):
    changed = repository.set_request_status(
        contract_request.id, "DOCUMENTS_UPLOADED", "phase1-test", "test transition"
    )
    assert changed.status == "DOCUMENTS_UPLOADED"
    events = repository.list_audit_events(contract_request.id)
    assert any(
        event.event_type == "REQUEST_STATUS_CHANGED"
        and event.details["from"] == "DRAFT"
        and event.details["to"] == "DOCUMENTS_UPLOADED"
        for event in events
    )


def test_repository_rejects_invalid_transition(repository, contract_request):
    with pytest.raises(ValueError, match="Invalid workflow transition"):
        repository.set_request_status(contract_request.id, "APPROVED", "tester", "invalid")


def test_repository_contract(repository, contract_request):
    rid = contract_request.id
    assert repository.get_request(rid).id == rid
    assert any(item.id == rid for item in repository.list_requests())

    document = Document(
        request_id=rid,
        doc_type="TAX_FORM",
        file_name="fake.pdf",
        storage_path=f"{rid}/fake.pdf",
        sha256="a" * 64,
        text_quality={"score": 0.9},
    )
    document = repository.add_document(document)
    assert repository.list_documents(rid)[0].id == document.id

    field = ExtractedFieldRecord(
        request_id=rid,
        document_id=document.id,
        field_name="legal_name",
        value="Test Fixture Vendor",
        confidence=Decimal("0.9"),
        status=ExtractedStatus.FOUND,
        evidence={"quote": "Test Fixture Vendor"},
        review_status=ReviewStatus.PENDING,
    )
    repository.save_extracted_fields(rid, document.id, [field])
    assert repository.list_extracted_fields(rid)[0].value == "Test Fixture Vendor"
    replacement = field.model_copy(update={"value": "Corrected Fixture Vendor"})
    repository.save_extracted_fields(rid, document.id, [replacement])
    assert [x.value for x in repository.list_extracted_fields(rid)] == ["Corrected Fixture Vendor"]

    finding = FindingRecord(
        request_id=rid,
        code="TEST",
        severity="INFO",
        message="Synthetic finding",
        source="DETERMINISTIC",
    )
    repository.save_findings(rid, "DETERMINISTIC", [finding])
    assert repository.list_findings(rid)[0].code == "TEST"
    repository.save_findings(rid, "DETERMINISTIC", [])
    assert repository.list_findings(rid) == []

    verification = VerificationResultRecord(
        request_id=rid, capability="sanctions", provider_name="fixture",
        mode="LOCAL_SIMULATED", status="VERIFIED", details={"simulation": "test"},
    )
    repository.save_verification_results(rid, [verification])
    assert repository.list_verification_results(rid)[0].capability == "sanctions"
    repository.save_verification_results(rid, [])
    assert repository.list_verification_results(rid) == []

    risk = RiskAssessmentRecord(request_id=rid, score=12, label="LOW")
    repository.save_risk_assessment(risk)
    assert repository.get_latest_risk_assessment(rid).score == 12
    approval = Approval(
        request_id=rid,
        stage=ApprovalStage.PROCUREMENT,
        approver_id="fictional-reviewer",
        decision=ApprovalDecision.APPROVE,
    )
    repository.add_approval(approval)
    assert repository.list_approvals(rid)[0].approver_id == "fictional-reviewer"

    event = AuditEvent(
        request_id=rid,
        actor="fixture",
        actor_type=ActorType.SYSTEM,
        event_type="FIXTURE_EVENT",
    )
    repository.append_audit_event(event)
    assert any(x.id == event.id for x in repository.list_audit_events(rid))
    assert all(isinstance(x, Vendor) for x in repository.list_vendors())
    assert all(
        item.name and item.list_name for item in repository.list_sanctions_entries()
    )

    run = AgentRun(
        request_id=rid,
        agent_name="fixture",
        status="OK",
        input_hash="b" * 64,
        output={"fixture": True},
        duration_ms=1,
    )
    assert repository.save_agent_run(run).id == run.id
    vendor_draft = VendorDraftRecord(request_id=rid, draft={"legal_name": "Fixture"})
    po_draft = PODraftRecord(request_id=rid, draft={"currency": "TST"})
    repository.save_vendor_draft(vendor_draft)
    repository.save_po_draft(po_draft)
    assert repository.get_vendor_draft(rid).draft["legal_name"] == "Fixture"
    assert repository.get_po_draft(rid).draft["currency"] == "TST"


def test_memory_audit_events_are_append_only_and_immutable():
    repo = InMemoryRepository()
    request = repo.create_request(VendorRequest(request_type=RequestType.NEW_SUPPLIER))
    event = repo.append_audit_event(
        AuditEvent(request_id=request.id, actor="x", actor_type="SYSTEM", event_type="CREATED")
    )
    with pytest.raises(ValidationError):
        event.event_type = "CHANGED"
    with pytest.raises(AttributeError):
        repo._audit_events.pop()
    assert repo.list_audit_events(request.id)[0].event_type == "CREATED"


def test_local_document_storage_round_trip_and_traversal_block():
    root = Path(__file__).resolve().parent
    storage = LocalDocumentStorage(root)
    path = f"storage-check-{uuid4()}.bin"
    try:
        storage.upload(path, b"synthetic", "application/octet-stream")
        assert storage.exists(path)
        assert storage.download(path) == b"synthetic"
        with pytest.raises(ValueError, match="inside"):
            storage.upload("../escape.txt", b"x")
    finally:
        (root / path).unlink(missing_ok=True)



