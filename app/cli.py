"""Offline case runner. Fake-live requests terminate at an in-process MockTransport."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.integrations.http.testing import fake_live_registry, local_demo_registry
from app.llm.factory import get_llm_provider
from app.llm.mock_provider import MockProvider
from app.repositories.factory import get_repository
from app.repositories.memory import InMemoryRepository
from app.schemas.domain import (
    ActorType,
    AuditEvent,
    Document,
    ReviewStatus,
    SanctionsEntry,
    Vendor,
    VendorRequest,
)
from app.schemas.review import ApproverRole, HumanDecision, HumanDecisionType
from app.service import VendorOnboardingAgentService

CASE_ROOT = Path(__file__).resolve().parents[1] / "demo" / "cases"


def _cases():
    return sorted(path.name for path in CASE_ROOT.iterdir() if path.is_dir())


def _load_fixtures(path: Path):
    raw = json.loads((path / "llm_fixtures.json").read_text(encoding="utf-8"))
    by_type = raw["document_extraction"]
    return MockProvider({"document_extraction": lambda **kwargs: next(
        value for key, value in by_type.items() if f"Declared document type: {key}" in kwargs["user"]
    )})


def _seed(repo, settings):
    if isinstance(repo, InMemoryRepository):
        repo.vendors = [Vendor(legal_name="ACME Supplies Private Limited", tax_id="SYN-TAX-ACME-001", country="IN")]
        repo.sanctions_entries = [SanctionsEntry(name="Example Restricted Trading Company", aliases=["ERTC"], list_name="fictional-demo-list")]
    return repo


def _make_registry(mode, repo, case_name):
    unavailable = "bank_account" if case_name == "bank_verification_unavailable" else None
    if mode == "fake-live":
        return fake_live_registry(repo.list_sanctions_entries(), unavailable=unavailable)
    return local_demo_registry(repo.list_sanctions_entries(), unavailable=unavailable)


def _run_case(name, args):
    case = CASE_ROOT / name
    if not case.is_dir():
        raise SystemExit(f"Unknown demo case: {name}")
    settings = Settings(repository_backend=args.repo, llm_provider=args.provider)
    repo = _seed(get_repository(settings), settings)
    fixtures = json.loads((case / "request.json").read_text(encoding="utf-8"))
    request_data = dict(fixtures["request"])
    request_data["id"] = str(uuid4())
    request = repo.create_request(VendorRequest(**request_data))
    for meta in fixtures["documents"]:
        content = (case / "documents" / meta["file_name"]).read_text(encoding="utf-8")
        repo.add_document(Document(
            request_id=request.id, doc_type=meta["doc_type"], file_name=meta["file_name"],
            storage_path=f"demo/{request.id}/{meta['file_name']}", text_content=content,
        ))
    provider = _load_fixtures(case) if args.provider == "mock" else get_llm_provider(settings)
    service = VendorOnboardingAgentService(
        settings, repository=repo, verification_registry=_make_registry(args.verification_mode, repo, name),
        llm_provider=provider,
    )
    assessment = service.process_request(request.id)
    if repo.list_extracted_fields(request.id) and repo.get_request(request.id).status != "BLOCKED":
        # Demo bundle represents a human-reviewed fixture; write the simulated action explicitly.
        grouped = {}
        for field in repo.list_extracted_fields(request.id):
            grouped.setdefault(field.document_id, []).append(field.model_copy(update={"review_status": ReviewStatus.CONFIRMED, "reviewed_by": "synthetic-demo-reviewer"}))
        for document_id, fields in grouped.items():
            repo.save_extracted_fields(request.id, document_id, fields)
        repo.append_audit_event(AuditEvent(
            request_id=request.id, actor="synthetic-demo-reviewer", actor_type=ActorType.HUMAN,
            event_type="DEMO_FIELD_REVIEW_SIMULATED",
            details={"review_status": "CONFIRMED", "fictional_fixture": True},
        ))
        if repo.get_request(request.id).status == "REWORK":
            repo.set_request_status(request.id, "DOCUMENTS_UPLOADED", "synthetic-demo-reviewer", "Synthetic demo rework response supplied reviewed fields.")
        assessment = service.resume_after_field_review(request.id)
    package = service.get_review_package(request.id)
    decisions = []
    if args.approve_all and not assessment.risk_assessment.risk.blocked:
        stage_actors = {
            "PROCUREMENT": (request.procurement_owner_id, ApproverRole.PROCUREMENT),
            "BUDGET_OWNER": (request.budget_owner_id, ApproverRole.BUDGET_OWNER),
            "FINANCE_HEAD": ("demo-finance-head", ApproverRole.FINANCE_HEAD),
        }
        for stage in package.required_stages:
            stage_value = stage.value
            actor, role = stage_actors[stage_value]
            decision = HumanDecision(stage=stage, approver_id=actor, approver_role=role,
                decision=HumanDecisionType.APPROVE, comment="Synthetic offline demo approval.")
            decisions.append(service.submit_decision(request.id, decision).model_dump(mode="json"))
        vendor_draft, po_draft = service.generate_drafts(request.id)
    else:
        vendor_draft = po_draft = None
    report = service.get_report(request.id)
    result = {
        "case": name, "request_id": request.id, "supplier": request.legal_name,
        "status": repo.get_request(request.id).status,
        "assessment": assessment.model_dump(mode="json"),
        "review_package": package.model_dump(mode="json"),
        "approvals": decisions,
        "drafts": {"vendor": vendor_draft.model_dump(mode="json") if vendor_draft else None,
                   "purchase_order": po_draft.model_dump(mode="json") if po_draft else None},
        "report": report,
    }
    print(json.dumps(result if args.json else _summary(result), indent=2, default=str))


def _summary(result):
    a = result["assessment"]
    return {
        "case": result["case"], "request_id": result["request_id"], "status": result["status"],
        "extracted_fields": [{"field": f["field_name"], "value": f["value"], "confidence": f["confidence"]} for f in a["extracted_data"]],
        "findings": [{"code": f["code"], "severity": f["severity"]} for f in a["validation_findings"]],
        "risk_score": a["risk_assessment"]["risk"]["score"], "risk_label": a["risk_assessment"]["risk"]["label"],
        "hard_blocks": a["risk_assessment"]["risk"]["hard_blocks"],
        "verification": a["verification_summary"], "next_action": a["recommended_next_action"],
        "human_review_required": a["human_review_required"], "approval_decisions": result["approvals"],
        "approval_stages": {
            "required": result["review_package"]["required_stages"],
            "completed": result["review_package"]["completed_stages"],
        },
        "drafts": result["drafts"], "audit_timeline": result["report"]["audit_timeline"],
    }


def _reset_demo(args):
    settings = Settings(repository_backend=args.repo)
    repo = get_repository(settings)
    if isinstance(repo, InMemoryRepository):
        print("Memory repository is process-local; no persistent demo rows to reset.")
        return
    removed = preserved = 0
    for request in repo.list_requests():
        if not request.is_demo:
            continue
        if repo.list_audit_events(request.id):
            preserved += 1
            continue
        client = repo.client
        for table in ("vendor_drafts", "po_drafts", "approvals", "risk_assessments", "findings", "verification_results", "extracted_fields", "agent_runs", "documents"):
            client.table(table).delete().eq("request_id", request.id).execute()
        client.table("vendor_requests").delete().eq("id", request.id).eq("is_demo", True).execute()
        removed += 1
    print(json.dumps({"demo_requests_removed": removed, "requests_preserved_with_audit_history": preserved}))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list-cases")
    run = sub.add_parser("run-case")
    run.add_argument("case")
    run.add_argument("--provider", choices=("mock", "groq"), default="mock")
    run.add_argument("--repo", choices=("memory", "supabase"), default="memory")
    run.add_argument("--verification-mode", choices=("local", "fake-live"), default="local")
    run.add_argument("--approve-all", action="store_true")
    run.add_argument("--json", action="store_true")
    reset = sub.add_parser("reset-demo")
    reset.add_argument("--repo", choices=("memory", "supabase"), default="memory")
    args = parser.parse_args(argv)
    if args.command == "list-cases":
        print("\n".join(_cases()))
    elif args.command == "run-case":
        _run_case(args.case, args)
    else:
        _reset_demo(args)


if __name__ == "__main__":
    main()
