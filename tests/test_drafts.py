from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.agents.po_draft import PODraftAgent
from app.agents.vendor_draft import VendorDraftAgent
from app.llm.errors import LLMProviderError
from app.llm.mock_provider import MockProvider
from app.repositories.memory import InMemoryRepository
from app.schemas.domain import (
    ActorType,
    Approval,
    ApprovalDecision,
    ApprovalStage,
    AuditEvent,
    ExtractedFieldRecord,
    ExtractedStatus,
    FindingRecord,
    RequestType,
    ReviewStatus,
    RiskAssessmentRecord,
    VendorRequest,
    VerificationResultRecord,
)
from app.schemas.findings import FindingCode
from app.services.draft_service import DraftGenerationError, DraftService
from app.services.report_service import ReportService, export_html
from app.workflow.states import WorkflowStatus
from scripts import export_report

ACCOUNT = "1234567890123456"
NORMALIZED = {"normalized_text": "14 Fictional Grove Sample City"}


def make_request(*, status=WorkflowStatus.APPROVED, high_value=False, blocked=False,
                 approvals=True, quotation=True, verification_mode="LOCAL_SIMULATED"):
    repo = InMemoryRepository()
    request = repo.create_request(VendorRequest(
        request_type=RequestType.SUPPLIER_WITH_PURCHASE,
        status=status.value,
        supplier_name="Fictional Trading Name",
        legal_name="Fictional Supplier Ltd",
        country="IN",
        tax_id="SYNTHETIC-TAX-123",
        address="14 Fictional Grove, Sample City",
        currency="INR",
        requester_id="requester",
        procurement_owner_id="procurement",
        budget_owner_id="budget",
        purchase_details={"demo": True},
    ))
    finding_codes = ([FindingCode.HIGH_VALUE_PURCHASE] if high_value else [])
    if blocked:
        finding_codes.append(FindingCode.SANCTIONS_MATCH)
    repo.save_findings(request.id, "DETERMINISTIC", [FindingRecord(
        request_id=request.id,
        code=code.value,
        severity="BLOCKING" if code == FindingCode.SANCTIONS_MATCH else "WARNING",
        message=f"Synthetic finding {code.value}.",
        source="DETERMINISTIC",
    ) for code in finding_codes])
    repo.save_risk_assessment(RiskAssessmentRecord(
        request_id=request.id,
        score=70 if blocked else 5,
        label="HIGH" if blocked else "LOW",
        hard_blocks=[FindingCode.SANCTIONS_MATCH.value] if blocked else [],
        blocked=blocked,
        contributions=[],
        explanation={"business_summary": "Synthetic readiness summary."},
    ))
    doc_id = "synthetic-quotation-document"
    fields = [
        ("registration_number", "REG-SYN-100"),
        ("company_type", "PRIVATE LIMITED"),
        ("address", "14 Fictional Grove, Sample City"),
        ("bank_name", "Synthetic National Bank"),
        ("branch", "Sample Branch"),
        ("account_number", ACCOUNT),
        ("routing_code", "SYNB0001234"),
        ("currency", "INR"),
        ("payment_terms", "Net 30 days"),
        ("email", "ap@example.invalid"),
    ]
    if quotation:
        fields.extend([
            ("line_items[0].description", "Premium sample widgets"),
            ("line_items[0].quantity", "2"),
            ("line_items[0].unit_price", "100.00"),
            ("line_items[0].tax", "18%"),
            ("total", "250.00"),
            ("delivery_date", "2027-04-30"),
        ])
    repo.save_extracted_fields(request.id, doc_id, [ExtractedFieldRecord(
        request_id=request.id,
        document_id=doc_id,
        field_name=name,
        value=value,
        confidence=Decimal("0.99"),
        status=ExtractedStatus.FOUND,
        evidence={"document_id": doc_id, "field_name": name, "quote": f"{name}: {value}"},
        review_status=ReviewStatus.CONFIRMED,
        reviewed_by="synthetic-reviewer",
    ) for name, value in fields])
    repo.save_verification_results(request.id, [VerificationResultRecord(
        request_id=request.id,
        capability="bank_account",
        provider_name="fictional_local_bank_fixture" if verification_mode == "LOCAL_SIMULATED" else "fictional_live_fixture",
        mode=verification_mode,
        status="VERIFIED",
        details={"raw_response": {"account_number": ACCOUNT, "token": "SYNTHETIC-SECRET"}},
    )])
    if approvals:
        repo.add_approval(Approval(
            request_id=request.id, stage=ApprovalStage.PROCUREMENT,
            approver_id="procurement", approver_role="PROCUREMENT",
            decision=ApprovalDecision.APPROVE, comment="Reviewed synthetic package.",
        ))
        repo.add_approval(Approval(
            request_id=request.id, stage=ApprovalStage.BUDGET_OWNER,
            approver_id="budget", approver_role="BUDGET_OWNER",
            decision=ApprovalDecision.APPROVE, comment="Reviewed synthetic budget.",
        ))
        if high_value:
            repo.add_approval(Approval(
                request_id=request.id, stage=ApprovalStage.FINANCE_HEAD,
                approver_id="finance", approver_role="FINANCE_HEAD",
                decision=ApprovalDecision.APPROVE, comment="Reviewed synthetic high-value purchase.",
            ))
    provider = MockProvider(responses={"draft_text_normalization": NORMALIZED})
    service = DraftService(
        repo,
        VendorDraftAgent(provider),
        PODraftAgent(provider),
    )
    return repo, request, service, provider


def test_approved_clean_request_generates_version_one_vendor_and_po_drafts():
    repo, request, service, _ = make_request()
    vendor, po = service.generate_drafts(request.id)
    assert vendor.status == po.status == "DRAFT"
    assert vendor.version == po.version == 1
    assert len(vendor.approval_references) == len(po.approval_references) == 2
    assert repo.get_request(request.id).status == WorkflowStatus.DRAFTS_GENERATED.value
    assert repo.get_vendor_draft(request.id).draft["version"] == 1
    assert repo.get_po_draft(request.id).draft["version"] == 1


@pytest.mark.parametrize("status", [
    WorkflowStatus.DRAFT,
    WorkflowStatus.PENDING_PROCUREMENT,
    WorkflowStatus.PENDING_BUDGET,
    WorkflowStatus.BLOCKED,
    WorkflowStatus.REJECTED,
])
def test_non_approved_blocked_and_rejected_requests_are_refused(status):
    repo, request, service, _ = make_request(status=status, blocked=status == WorkflowStatus.BLOCKED)
    with pytest.raises(DraftGenerationError):
        service.generate_drafts(request.id)
    assert repo.list_vendor_drafts(request.id) == []
    assert repo.list_po_drafts(request.id) == []


def test_approved_status_still_requires_complete_approval_set():
    repo, request, service, _ = make_request(approvals=False)
    repo.add_approval(Approval(
        request_id=request.id, stage=ApprovalStage.PROCUREMENT,
        approver_id="procurement", approver_role="PROCUREMENT", decision=ApprovalDecision.APPROVE,
        comment="Synthetic procurement approval.",
    ))
    with pytest.raises(DraftGenerationError, match="missing or duplicated: BUDGET_OWNER"):
        service.generate_drafts(request.id)


def test_high_value_requires_finance_approval_and_then_generates_drafts():
    repo, request, service, _ = make_request(high_value=True, approvals=False)
    for stage, approver, role in (
        (ApprovalStage.PROCUREMENT, "procurement", "PROCUREMENT"),
        (ApprovalStage.BUDGET_OWNER, "budget", "BUDGET_OWNER"),
    ):
        repo.add_approval(Approval(
            request_id=request.id, stage=stage, approver_id=approver,
            approver_role=role, decision=ApprovalDecision.APPROVE,
            comment="Synthetic required-stage approval.",
        ))
    with pytest.raises(DraftGenerationError, match="FINANCE_HEAD"):
        service.generate_drafts(request.id)
    repo.add_approval(Approval(
        request_id=request.id, stage=ApprovalStage.FINANCE_HEAD,
        approver_id="finance", approver_role="FINANCE_HEAD", decision=ApprovalDecision.APPROVE,
        comment="Synthetic finance approval.",
    ))
    vendor, po = service.generate_drafts(request.id)
    assert len(vendor.approval_references) == len(po.approval_references) == 3


def test_draft_generation_refuses_authoritative_hard_blocks_even_if_status_approved():
    _, request, service, _ = make_request(blocked=True)
    with pytest.raises(DraftGenerationError, match="Hard-blocked"):
        service.generate_drafts(request.id)


def test_draft_versions_are_appended_and_version_one_remains_available():
    repo, request, service, _ = make_request()
    first_vendor, first_po = service.generate_drafts(request.id)
    second_vendor, second_po = service.generate_revision(request.id)
    assert (first_vendor.version, second_vendor.version) == (1, 2)
    assert (first_po.version, second_po.version) == (1, 2)
    assert [item.version for item in repo.list_vendor_drafts(request.id)] == [1, 2]
    assert [item.version for item in repo.list_po_drafts(request.id)] == [1, 2]
    assert repo.list_vendor_drafts(request.id)[0].draft["version"] == 1


def test_full_bank_account_is_absent_from_both_draft_serializations():
    _, request, service, _ = make_request()
    vendor, po = service.generate_drafts(request.id)
    assert ACCOUNT not in vendor.model_dump_json()
    assert vendor.bank.account_number_masked == "****3456"
    assert ACCOUNT not in po.model_dump_json()


def test_vendor_draft_only_uses_reviewed_values_and_llm_cannot_change_identity_fields():
    repo, request, service, provider = make_request()
    fields = repo.list_extracted_fields(request.id)
    for field in fields:
        if field.field_name == "tax_id":
            field.value = "MUST-NOT-CHANGE-TAX"
            field.review_status = ReviewStatus.PENDING
    repo.save_extracted_fields(request.id, fields[0].document_id, fields)
    vendor, _ = service.generate_drafts(request.id)
    assert vendor.tax_id == request.tax_id
    assert vendor.bank.account_number_masked == "****3456"
    assert "MUST-NOT-CHANGE-TAX" not in str(provider.calls)
    assert all("1234567890123456" not in call["user"] for call in provider.calls)


def test_quotation_totals_are_deterministic_and_mismatch_is_a_warning():
    _, request, service, _ = make_request()
    _, po = service.generate_drafts(request.id)
    assert po.subtotal == Decimal("200.00")
    assert po.tax_total == Decimal("36.00")
    assert po.total == Decimal("236.00")
    assert po.line_items[0].line_total == Decimal("236.00")
    assert any("differs from quotation total 250.00" in warning for warning in po.warnings)


def test_vendor_address_normalization_failure_falls_back_and_warns():
    repo, request, _, _ = make_request()
    failing = MockProvider(fail_with=LLMProviderError("synthetic offline failure"))
    service = DraftService(repo, VendorDraftAgent(failing), PODraftAgent(failing))
    vendor, po = service.generate_drafts(request.id)
    assert vendor.address == "14 Fictional Grove, Sample City"
    assert any("Address normalization was unavailable" in warning for warning in vendor.warnings)
    assert po.line_items[0].description == "Premium sample widgets"
    assert any("Line description normalization failed" in warning for warning in po.warnings)


def test_llm_cannot_inject_new_address_or_line_item_text():
    repo, request, _, _ = make_request()
    hostile = MockProvider(responses={
        "draft_text_normalization": {"normalized_text": "Fictional Supplier payment account 999999999999"},
    })
    service = DraftService(repo, VendorDraftAgent(hostile), PODraftAgent(hostile))
    vendor, po = service.generate_drafts(request.id)
    assert vendor.address == "14 Fictional Grove, Sample City"
    assert po.line_items[0].description == "Premium sample widgets"
    assert any("Address normalization was unavailable" in item for item in vendor.warnings)
    assert any("changed source words" in item for item in po.warnings)


@pytest.mark.parametrize("mode,has_simulated_warning", [
    ("LOCAL_SIMULATED", True),
    ("LIVE", False),
])
def test_vendor_draft_simulation_warning_matches_verification_mode(mode, has_simulated_warning):
    _, request, service, _ = make_request(verification_mode=mode)
    vendor, _ = service.generate_drafts(request.id)
    assert any("LOCAL_SIMULATED" in warning for warning in vendor.warnings) is has_simulated_warning
    assert vendor.verification_status[0].mode.value == mode


def test_report_is_json_safe_masked_and_excludes_raw_verification_payloads():
    repo, request, service, _ = make_request()
    service.generate_drafts(request.id)
    report = ReportService(repo).build_report(request.id)
    serialized = __import__("json").dumps(report)
    assert ACCOUNT not in serialized
    assert "SYNTHETIC-SECRET" not in serialized
    assert "raw_response" not in serialized
    assert report["verification_provenance"][0]["mode"] == "LOCAL_SIMULATED"
    assert "details" not in report["verification_provenance"][0]


def test_live_provenance_report_is_distinguished_and_html_masks_account():
    repo, request, service, _ = make_request(verification_mode="LIVE")
    service.generate_drafts(request.id)
    report = ReportService(repo).build_report(request.id)
    html = export_html(report)
    assert ACCOUNT not in html
    assert "LIVE" in html
    assert "LOCAL_SIMULATED" in html
    assert "SYNTHETIC-SECRET" not in html


def test_report_export_cli_writes_requested_html_path(monkeypatch):
    repo, request, service, _ = make_request()
    service.generate_drafts(request.id)
    monkeypatch.setattr(export_report, "get_repository", lambda: repo)
    output = Path(__file__).with_name(f"phase7-report-{uuid4().hex}.html")
    try:
        monkeypatch.setattr("sys.argv", ["export_report", request.id, "--out", str(output)])
        assert export_report.main() == 0
        assert output.exists()
        assert "Vendor onboarding readiness report" in output.read_text(encoding="utf-8")
    finally:
        output.unlink(missing_ok=True)


def test_report_audit_timeline_is_chronological_and_draft_events_are_preserved():
    repo, request, service, _ = make_request()
    later = datetime.now(UTC)
    earlier = later - timedelta(minutes=1)
    repo.append_audit_event(AuditEvent(
        request_id=request.id, actor="synthetic-later", actor_type=ActorType.HUMAN,
        event_type="SYNTHETIC_LATER", created_at=later,
    ))
    repo.append_audit_event(AuditEvent(
        request_id=request.id, actor="synthetic-earlier", actor_type=ActorType.SYSTEM,
        event_type="SYNTHETIC_EARLIER", created_at=earlier,
    ))
    service.generate_drafts(request.id)
    timeline = ReportService(repo).build_report(request.id)["audit_timeline"]
    timestamps = [item["timestamp"] for item in timeline]
    assert timestamps == sorted(timestamps)
    assert {"VENDOR_DRAFT_GENERATED", "PO_DRAFT_GENERATED", "REQUEST_STATUS_CHANGED"} <= {
        item["event_type"] for item in timeline
    }


def test_status_transitions_only_after_both_drafts_persist_and_failure_does_not_transition():
    class FailingPORepository(InMemoryRepository):
        def save_po_draft(self, draft):
            raise RuntimeError("synthetic PO persistence failure")

    base, request, service, _ = make_request()
    failing = FailingPORepository()
    failing.requests = base.requests
    failing.extracted_fields = base.extracted_fields
    failing.findings = base.findings
    failing.risk_assessments = base.risk_assessments
    failing.verification_results = base.verification_results
    failing.approvals = base.approvals
    failing_service = DraftService(failing, service.vendor_agent, service.po_agent)
    with pytest.raises(RuntimeError, match="synthetic PO persistence failure"):
        failing_service.generate_drafts(request.id)
    assert failing.get_request(request.id).status == WorkflowStatus.APPROVED.value
    assert failing.list_vendor_drafts(request.id)
    assert failing.list_po_drafts(request.id) == []
    assert not any(event.event_type == "REQUEST_STATUS_CHANGED" for event in failing.list_audit_events(request.id))


def test_approval_provenance_requires_distinct_owners_and_valid_roles():
    repo, request, service, _ = make_request()
    repo.requests[request.id] = repo.requests[request.id].model_copy(
        update={"budget_owner_id": "procurement"}
    )
    approvals = repo.list_approvals(request.id)
    approvals[1] = approvals[1].model_copy(update={"approver_id": "procurement"})
    repo.approvals = {item.id: item for item in approvals}
    with pytest.raises(DraftGenerationError, match="same person"):
        service.generate_drafts(request.id)
