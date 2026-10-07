"""Exercise Phase 7 draft and report behavior with fictional in-memory records."""

from decimal import Decimal

from app.agents.po_draft import PODraftAgent
from app.agents.vendor_draft import VendorDraftAgent
from app.llm.errors import LLMProviderError
from app.llm.mock_provider import MockProvider
from app.repositories.memory import InMemoryRepository
from app.schemas.domain import (
    Approval,
    ApprovalDecision,
    ApprovalStage,
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


def make_case(label, *, status=WorkflowStatus.APPROVED, high_value=False,
              blocked=False, approved_stages=None, llm_failure=False,
              verification_mode="LOCAL_SIMULATED", quote_total="354.00"):
    repo = InMemoryRepository()
    request = repo.create_request(VendorRequest(
        request_type=RequestType.SUPPLIER_WITH_PURCHASE,
        status=status.value,
        supplier_name="Fictional Sample Trading",
        legal_name="Fictional Sample Supplier Ltd",
        country="IN",
        tax_id="SYNTHETIC-TAX-4455",
        address="11 Example Road, Sample City",
        currency="INR",
        requester_id="demo-requester",
        procurement_owner_id="demo-procurement",
        budget_owner_id="demo-budget",
        is_demo=True,
    ))
    codes = [FindingCode.HIGH_VALUE_PURCHASE] if high_value else []
    if blocked:
        codes.append(FindingCode.SANCTIONS_MATCH)
    repo.save_findings(request.id, "DETERMINISTIC", [FindingRecord(
        request_id=request.id, code=code.value,
        severity="BLOCKING" if code == FindingCode.SANCTIONS_MATCH else "WARNING",
        message=f"Synthetic demo finding: {code.value}.", source="DETERMINISTIC",
    ) for code in codes])
    repo.save_risk_assessment(RiskAssessmentRecord(
        request_id=request.id, score=65 if blocked else 10,
        label="HIGH" if blocked else "LOW",
        hard_blocks=[FindingCode.SANCTIONS_MATCH.value] if blocked else [],
        blocked=blocked, explanation={"business_summary": "Fictional offline demo assessment."},
    ))
    fields = [
        ("registration_number", "DEMO-REG-0007"),
        ("address", "11 Example Road, Sample City"),
        ("account_number", "9876543210012345"),
        ("bank_name", "Fictional Sample Bank"),
        ("routing_code", "DEMO0001234"),
        ("currency", "INR"),
        ("payment_terms", "Net 30"),
        ("line_items[0].description", "Fictional demo equipment"),
        ("line_items[0].quantity", "3"),
        ("line_items[0].unit_price", "100.00"),
        ("line_items[0].tax", "18%"),
        ("total", quote_total),
    ]
    repo.save_extracted_fields(request.id, "demo-quotation", [ExtractedFieldRecord(
        request_id=request.id,
        document_id="demo-quotation",
        field_name=name,
        value=value,
        confidence=Decimal("0.99"),
        status=ExtractedStatus.FOUND,
        evidence={"document_id": "demo-quotation", "field_name": name, "quote": f"{name}: {value}"},
        review_status=ReviewStatus.CONFIRMED,
        reviewed_by="demo-reviewer",
    ) for name, value in fields])
    repo.save_verification_results(request.id, [VerificationResultRecord(
        request_id=request.id,
        capability="bank_account",
        provider_name="fictional_demo_bank_adapter",
        mode=verification_mode,
        status="VERIFIED",
    )])
    stage_rows = approved_stages
    if stage_rows is None:
        stage_rows = [ApprovalStage.PROCUREMENT, ApprovalStage.BUDGET_OWNER]
        if high_value:
            stage_rows.append(ApprovalStage.FINANCE_HEAD)
    actors = {
        ApprovalStage.PROCUREMENT: ("demo-procurement", "PROCUREMENT"),
        ApprovalStage.BUDGET_OWNER: ("demo-budget", "BUDGET_OWNER"),
        ApprovalStage.FINANCE_HEAD: ("demo-finance", "FINANCE_HEAD"),
    }
    for stage in stage_rows:
        actor, role = actors[stage]
        repo.add_approval(Approval(
            request_id=request.id, stage=stage, approver_id=actor, approver_role=role,
            decision=ApprovalDecision.APPROVE, comment="Fictional demo reviewer approved.",
        ))
    def normalize_text(*, user, **_kwargs):
        normalized = (
            "11 Example Road Sample City"
            if "address" in user.casefold()
            else "Fictional demo equipment"
        )
        return {"normalized_text": normalized}

    responses = {} if llm_failure else {"draft_text_normalization": normalize_text}
    provider = MockProvider(
        responses=responses,
        fail_with=LLMProviderError("synthetic demo failure") if llm_failure else None,
    )
    service = DraftService(repo, VendorDraftAgent(provider), PODraftAgent(provider))
    print(f"\n{label}")
    print(f"  request ID: {request.id}")
    print(f"  request status: {request.status}")
    print(f"  approval references: {[item.id for item in repo.list_approvals(request.id)]}")
    return repo, request, service


def run_generation(repo, request, service):
    try:
        vendor, po = service.generate_drafts(request.id)
    except DraftGenerationError as exc:
        print(f"  generation refused: {exc}")
        vendor = po = None
    if vendor and po:
        print(f"  vendor draft: {vendor.status} v{vendor.version}")
        print(f"  PO draft: {po.status} v{po.version} ({po.draft_po_reference})")
        print(f"  verification provenance: {[item.model_dump(mode='json') for item in vendor.verification_status]}")
        print(f"  vendor warnings: {vendor.warnings}")
        print(f"  PO warnings: {po.warnings}")
        print(f"  totals: subtotal={po.subtotal} tax={po.tax_total} total={po.total} {po.currency}")
    report = ReportService(repo).build_report(request.id)
    print(f"  report generation status: {'success' if export_html(report) else 'failed'}")
    print(f"  final request status: {repo.get_request(request.id).status}")
    return vendor, po


def main():
    repo, request, service = make_case("clean approved request")
    vendor, po = run_generation(repo, request, service)
    if vendor and po:
        vendor2, po2 = service.generate_revision(request.id)
        print(f"  versioning: vendor v{vendor.version} retained; new v{vendor2.version}; PO v{po.version} retained; new v{po2.version}")

    repo, request, service = make_case("high-value approved request", high_value=True)
    run_generation(repo, request, service)

    repo, request, service = make_case("blocked request", status=WorkflowStatus.BLOCKED, blocked=True)
    run_generation(repo, request, service)

    repo, request, service = make_case("rejected request", status=WorkflowStatus.REJECTED)
    run_generation(repo, request, service)

    repo, request, service = make_case(
        "partially approved request", status=WorkflowStatus.PENDING_BUDGET,
        approved_stages=[ApprovalStage.PROCUREMENT],
    )
    run_generation(repo, request, service)

    repo, request, service = make_case("quotation mismatch", quote_total="999.00")
    run_generation(repo, request, service)

    repo, request, service = make_case("live verification provenance", verification_mode="LIVE")
    run_generation(repo, request, service)

    repo, request, service = make_case("LLM failure fallback", llm_failure=True)
    run_generation(repo, request, service)


if __name__ == "__main__":
    main()
