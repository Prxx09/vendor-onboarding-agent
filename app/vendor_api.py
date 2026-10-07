from __future__ import annotations

from typing import Any
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app import storage
from app.data import add_audit, create_case_from_intake, find_case, list_audit, list_cases
from app.extraction import extract_documents
from app.main import _validate_documents, LOCAL_FILES

router = APIRouter(prefix="/api/v1/vendors", tags=["vendors"])

REQUIRED_DOCUMENTS = {
    "business_registration": "Business Registration",
    "tax_certificate": "Tax Certificate",
    "bank_proof": "Cancelled Cheque / Bank Proof",
}


class ReviewPayload(BaseModel):
    decision: str
    reviewer: str = "Reviewer"
    comment: str = ""


def _all_cases() -> list[dict[str, Any]]:
    cases = list_cases()
    if storage.configured():
        try:
            known = {item["id"] for item in cases}
            cases.extend(item for item in storage.list_cases() if item["id"] not in known)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return sorted(cases, key=lambda item: item.get("submitted_at", ""), reverse=True)


def _get_case(case_id: str) -> dict[str, Any]:
    case = find_case(case_id)
    if storage.configured():
        try:
            stored = storage.find_case(case_id)
            if stored:
                case = {**(case or {}), **stored}
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not case:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return case


def _status(case: dict[str, Any]) -> str:
    status = str(case.get("status") or "").upper()
    return {
        "AUTO_APPROVED": "APPROVED",
        "APPROVED": "APPROVED",
        "HUMAN_REVIEW": "REVIEW_REQUIRED",
        "REVIEW_REQUIRED": "REVIEW_REQUIRED",
        "NEEDS_INFO": "ACTION_REQUIRED",
        "ACTION_REQUIRED": "ACTION_REQUIRED",
        "REJECTED": "REJECTED",
    }.get(status, status or "REVIEW_REQUIRED")


def _recommendation(case: dict[str, Any]) -> str:
    status = _status(case)
    if status == "APPROVED":
        return "APPROVE"
    if status == "ACTION_REQUIRED":
        return "WAIT_FOR_DOCUMENTS"
    return "REJECT"


def _check_status(result: str) -> str:
    label = str(result or "").upper()
    if label in {"PASS", "PASSED", "VERIFIED"}:
        return "VERIFIED"
    if label in {"FAIL", "FAILED", "BLOCKED"}:
        return "MISMATCH"
    return "REVIEW_REQUIRED"


def _check_source(name: str) -> str:
    value = str(name or "").lower()
    if "tax" in value or "gst" in value:
        return "tax_registry"
    if "bank" in value:
        return "bank_account_registry"
    if "sanction" in value:
        return "sanctions_registry"
    if "compliance" in value or "kyc" in value:
        return "kyc_registry"
    if "document" in value or "registration" in value:
        return "company_registry"
    return "vendor_master_snapshot"


def _checks(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "source": _check_source(check.get("name", "")),
            "status": _check_status(check.get("result", "")),
            "message": check.get("detail") or check.get("message") or check.get("name") or "Verification completed.",
            "data": {"score": check.get("score")},
        }
        for check in case.get("checks", [])
    ]


def _events(case_id: str) -> list[dict[str, str]]:
    events = sorted(list_audit(case_id), key=lambda item: item.get("timestamp", ""))
    step_map = {
        "DOCUMENTS_UPLOADED": "intake",
        "DOCUMENT_UPLOADED": "intake",
        "INTAKE_SUBMITTED": "intake",
        "FIELDS_EXTRACTED": "document_extraction",
        "VALIDATION_COMPLETED": "external_verification",
        "AUTO_APPROVED": "decision",
        "APPROVED": "decision",
        "HUMAN_REVIEW": "decision",
        "HUMAN_REVIEW_REQUIRED": "decision",
        "REJECTED": "decision",
        "NEEDS_INFO": "completeness",
    }
    return [
        {
            "step": step_map.get(str(event.get("event_type", "")).upper(), "verification"),
            "message": event.get("message", ""),
        }
        for event in events
    ]


def _reasons(case: dict[str, Any]) -> list[str]:
    failed = [
        check.get("detail") or check.get("message") or check.get("name")
        for check in case.get("checks", [])
        if _check_status(check.get("result", "")) != "VERIFIED"
    ]
    if failed:
        return [str(item) for item in failed if item]
    if _status(case) == "APPROVED":
        return ["All required verification checks passed."]
    return ["Verification requires manual review."]


def _document_payload(doc: dict[str, Any], extracted: dict[str, Any] | None = None) -> dict[str, Any]:
    extracted = extracted or {}
    return {
        "filename": doc.get("name") or doc.get("filename") or "document",
        "document_type": doc.get("document_type") or doc.get("type") or "supporting_document",
        "confidence": extracted.get("confidence"),
        "extracted_data": extracted.get("extracted_data") or {},
    }


def _summary(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case["id"],
        "legal_name": case.get("vendor_name") or case.get("submitted_form", {}).get("legal_name") or "Unknown vendor",
        "status": _status(case),
        "agent_recommendation": _recommendation(case),
        "human_decision": case.get("human_decision"),
        "reasons": _reasons(case),
        "created_at": case.get("submitted_at"),
    }


@router.get("")
def list_vendors(status: str | None = None) -> list[dict[str, Any]]:
    values = [_summary(case) for case in _all_cases()]
    if status:
        wanted = status.upper()
        values = [item for item in values if item["status"] == wanted]
    return values


@router.get("/review-queue")
def review_queue() -> list[dict[str, Any]]:
    return [item for item in list_vendors() if item["status"] == "REVIEW_REQUIRED"]


@router.post("/process")
async def process_vendor(
    legal_name: str = Form(...),
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    documents = [
        (upload.filename or "vendor-document.pdf", await upload.read(), upload.content_type or "application/octet-stream")
        for upload in files
    ]
    _validate_documents(documents)

    try:
        extraction = extract_documents([(name, content) for name, content, _ in documents])
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    fields = extraction.get("extracted_fields", {})
    fields["legal_name"] = legal_name
    detected = {
        kind
        for document in extraction.get("documents", [])
        for kind in document.get("detected_types", [])
    }
    missing = [label for kind, label in REQUIRED_DOCUMENTS.items() if kind not in detected]

    payload = {
        "legal_name": legal_name,
        "tax_id": fields.get("tax_id", ""),
        "pan": fields.get("pan", ""),
        "bank_account": fields.get("bank_account", ""),
        "ifsc": fields.get("ifsc", ""),
        "registered_address": fields.get("registered_address", ""),
        "contact_email": fields.get("contact_email", ""),
        "category": "General",
        "region": "India",
        "submitted_by": "Vendor Portal",
        "document_name": documents[0][0],
        "document_names": [name for name, _, _ in documents],
        "compliance_confirmed": True,
        "extraction_confidence": extraction.get("extraction_confidence"),
    }
    case = create_case_from_intake(payload)

    if missing:
        target = find_case(case["id"])
        if target:
            target["status"] = "NEEDS_INFO"
            case["status"] = "NEEDS_INFO"
        add_audit(case["id"], "Completeness Agent", "NEEDS_INFO", "Missing required evidence: " + ", ".join(missing))

    if storage.configured():
        try:
            storage.save_intake(case, payload, documents)
            stored = storage.find_case(case["id"])
            if stored:
                case = {**case, **stored}
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Vendor was not stored: {exc}") from exc
    else:
        for index, (name, content, mime) in enumerate(documents):
            document_id = f"source-document-{index + 1}"
            LOCAL_FILES[(case["id"], document_id)] = (content, mime, name)

    per_doc = []
    for item in extraction.get("documents", []):
        doc_fields = item.get("fields", {})
        per_doc.append({
            "filename": item.get("name"),
            "document_type": item.get("document_type"),
            "confidence": round(sum(item.get("field_confidence", {}).values()) / max(1, len(item.get("field_confidence", {}))) / 100, 2),
            "legal_name": doc_fields.get("legal_name"),
            "registration_number": doc_fields.get("registration_number"),
            "tax_id": doc_fields.get("tax_id"),
            "account_holder_name": doc_fields.get("account_holder_name"),
            "bank_name": doc_fields.get("bank_name"),
            "bank_account_number": doc_fields.get("bank_account"),
            "ifsc_swift": doc_fields.get("ifsc"),
            "registered_address": doc_fields.get("registered_address"),
            "issue_date": doc_fields.get("issue_date"),
            "expiry_date": doc_fields.get("expiry_date"),
            "notes": [f"Text extracted via {item.get('method', 'document parser')}."],
        })

    return {
        "vendor_id": case["id"],
        "vendor_name": legal_name,
        "overall_status": _status(case),
        "recommendation": _recommendation(case),
        "missing_documents": missing,
        "extractions": per_doc,
        "checks": _checks(case),
        "reasons": _reasons(case),
        "events": _events(case["id"]),
    }


@router.get("/{vendor_id}")
def vendor_detail(vendor_id: str) -> dict[str, Any]:
    case = _get_case(vendor_id)
    form = case.get("submitted_form") or case.get("extracted_fields") or {}
    documents = [
        {
            "filename": doc.get("name"),
            "document_type": doc.get("type") or "supporting_document",
            "confidence": None,
            "extracted_data": {
                "legal_name": form.get("legal_name"),
                "tax_id": form.get("tax_id"),
                "bank_account_number": form.get("bank_account"),
                "ifsc_swift": form.get("ifsc"),
                "registered_address": form.get("registered_address"),
            },
        }
        for doc in case.get("documents", [])
    ]
    return {
        "vendor": _summary(case),
        "documents": documents,
        "agent_runs": [{
            "status": _status(case),
            "recommendation": _recommendation(case),
            "checks": _checks(case),
            "events": _events(vendor_id),
        }],
    }


@router.post("/{vendor_id}/review")
def review_vendor(vendor_id: str, payload: ReviewPayload) -> dict[str, Any]:
    normalized = payload.decision.upper()
    if normalized not in {"APPROVE", "REJECT"}:
        raise HTTPException(status_code=400, detail="Decision must be APPROVE or REJECT")

    final_status = "APPROVED" if normalized == "APPROVE" else "REJECTED"
    case = find_case(vendor_id)
    if storage.configured():
        try:
            updated = storage.save_decision(vendor_id, final_status, payload.reviewer)
            if updated:
                case = updated
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    if case is None:
        raise HTTPException(status_code=404, detail="Vendor not found")

    local_case = find_case(vendor_id)
    if local_case:
        local_case["status"] = final_status
        local_case["assigned_to"] = payload.reviewer
        local_case["human_decision"] = normalized
        case = local_case

    add_audit(
        vendor_id,
        payload.reviewer,
        f"HUMAN_{final_status}",
        payload.comment or f"Reviewer marked vendor as {final_status}.",
    )
    return {
        "vendor_id": vendor_id,
        "agent_recommendation": _recommendation(case),
        "human_decision": normalized,
        "final_status": final_status,
        "comment": payload.comment,
    }
