import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.repositories.base import OnboardingRepository
from app.schemas.domain import ApprovalDecision, ApprovalStage


class ReportService:
    def __init__(self, repo: OnboardingRepository) -> None:
        self.repo = repo

    def build_report(self, request_id: str) -> dict[str, Any]:
        request = self.repo.get_request(request_id)
        if request is None:
            raise KeyError(f"Request not found: {request_id}")
        risk_record = self.repo.get_latest_risk_assessment(request_id)
        risk = risk_record.model_dump(mode="json") if risk_record else None
        documents = self.repo.list_documents(request_id)
        document_types = {}
        for document in documents:
            document_types[document.id] = document.doc_type

        extracted = []
        for item in self.repo.list_extracted_fields(request_id):
            value = item.value
            if _sensitive_field(item.field_name):
                value = mask_secret(value)
            extracted.append({
                "id": item.id,
                "document_id": item.document_id,
                "document_type": document_types.get(item.document_id),
                "field_name": item.field_name,
                "value": _safe(value),
                "status": item.status.value,
                "review_status": item.review_status.value,
                "evidence": _safe(item.evidence),
            })
        findings = [
            _safe({
                "id": item.id,
                "code": item.code,
                "severity": item.severity,
                "message": item.message,
                "source": item.source,
                "evidence": item.evidence,
            })
            for item in self.repo.list_findings(request_id)
        ]
        verifications = [
            {
                "capability": item.capability,
                "provider": item.provider_name,
                "mode": item.mode,
                "status": item.status,
                "checked_at": item.checked_at.isoformat(),
            }
            for item in self.repo.list_verification_results(request_id)
        ]
        approvals = [
            _safe({
                "id": item.id,
                "stage": item.stage.value,
                "approver_id": item.approver_id,
                "approver_role": item.approver_role,
                "decision": item.decision.value if item.decision else None,
                "comment": item.comment,
                "created_at": item.created_at.isoformat(),
            })
            for item in sorted(self.repo.list_approvals(request_id), key=lambda row: row.created_at)
        ]
        vendor_drafts = [
            _safe(item.draft)
            for item in self.repo.list_vendor_drafts(request_id)
        ]
        po_drafts = [
            _safe(item.draft)
            for item in self.repo.list_po_drafts(request_id)
        ]
        timeline = []
        for event in sorted(self.repo.list_audit_events(request_id), key=lambda row: row.created_at):
            timeline.append(_safe({
                "timestamp": event.created_at.isoformat(),
                "actor": event.actor,
                "actor_type": event.actor_type.value,
                "event_type": event.event_type,
                "details": _public_audit_details(event.details),
            }))
        completed = [
            stage.value for stage in ApprovalStage
            if any(item.stage == stage and item.decision == ApprovalDecision.APPROVE
                   for item in self.repo.list_approvals(request_id))
        ]
        report = {
            "summary": {
                "request_id": request.id,
                "request_type": request.request_type.value,
                "status": request.status,
                "supplier_name": request.legal_name or request.supplier_name,
                "country": request.country,
                "approval_stages_completed": completed,
            },
            "masked_extracted_fields": extracted,
            "validation_findings": findings,
            "risk": _safe(risk),
            "verification_provenance": verifications,
            "approvals": approvals,
            "drafts": {"vendor": vendor_drafts, "purchase_order": po_drafts},
            "audit_timeline": timeline,
        }
        return _safe(report)


def export_html(report: dict[str, Any]) -> str:
    """Render an API-serializable report using an autoescaping Jinja template."""
    template_dir = Path(__file__).resolve().parents[1] / "templates"
    environment = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    return environment.get_template("onboarding_report.html").render(report=report)


def _sensitive_field(name: str) -> bool:
    return any(term in name.casefold() for term in ("account", "iban"))


def mask_secret(value: Any) -> Any:
    if value is None:
        return None
    from app.utils.masking import mask_account_number

    return mask_account_number(str(value))


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            normalized = str(key).casefold()
            if any(part in normalized for part in ("secret", "service_key", "raw_response", "provider_payload", "api_key")):
                continue
            safe[key] = mask_secret(item) if _sensitive_field(str(key)) else _safe(item)
        return safe
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_safe(item) for item in value]
    if isinstance(value, str):
        from app.services.review_service import _mask_labeled_accounts

        masked = _mask_labeled_accounts(value)
        return re.sub(r"(?<!\d)\d{8,30}(?!\d)", lambda match: f"****{match.group(0)[-4:]}", masked)
    return value


def _public_audit_details(details: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in details.items()
        if not any(
            hidden in str(key).casefold()
            for hidden in ("raw", "payload", "secret", "service_key", "api_key", "response_body")
        )
    }
