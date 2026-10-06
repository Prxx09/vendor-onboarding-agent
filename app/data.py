from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.workflow import (
    APPROVAL_THRESHOLD,
    calculate_confidence,
    route_case,
    score_checks,
)

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


DEMO_CASES: list[dict[str, Any]] = [
    {
        "id": "VO-1001",
        "vendor_name": "Apex Components Pvt Ltd",
        "category": "Manufacturing",
        "region": "India",
        "submitted_by": "Procurement Desk",
        "submitted_at": "2026-10-06T04:10:00+00:00",
        "status": "AUTO_APPROVED",
        "confidence": 94,
        "risk_level": "Low",
        "assigned_to": "Auto Approval Engine",
        "document": "apex-components-registration.pdf",
        "extracted_fields": {
            "legal_name": "Apex Components Pvt Ltd",
            "tax_id": "27AAPCA4587Q1Z3",
            "pan": "AAPCA4587Q",
            "bank_account": "XXXXXX2381",
            "ifsc": "HDFC0001342",
            "registered_address": "Pune, Maharashtra",
            "contact_email": "accounts@apexcomponents.example",
        },
        "checks": [
            {"name": "Document completeness", "score": 98, "result": "Pass", "detail": "All required documents are present."},
            {"name": "Tax ID verification", "score": 96, "result": "Pass", "detail": "GSTIN format and PAN linkage matched."},
            {"name": "Bank verification", "score": 92, "result": "Pass", "detail": "Account and IFSC format validated."},
            {"name": "Sanctions screening", "score": 99, "result": "Pass", "detail": "No exact or fuzzy match found."},
            {"name": "Compliance questionnaire", "score": 86, "result": "Pass", "detail": "Policy declarations accepted."},
        ],
    },
    {
        "id": "VO-1002",
        "vendor_name": "Northstar Facility Services",
        "category": "Facilities",
        "region": "India",
        "submitted_by": "Admin Team",
        "submitted_at": "2026-10-06T05:25:00+00:00",
        "status": "HUMAN_REVIEW",
        "confidence": 71,
        "risk_level": "Medium",
        "assigned_to": "Vendor Risk Reviewer",
        "document": "northstar-onboarding.zip",
        "extracted_fields": {
            "legal_name": "Northstar Facility Services",
            "tax_id": "27AANFN7214L1Z6",
            "pan": "AANFN7214L",
            "bank_account": "XXXXXX9012",
            "ifsc": "ICIC0000898",
            "registered_address": "Navi Mumbai, Maharashtra",
            "contact_email": "ops@northstarfacility.example",
        },
        "checks": [
            {"name": "Document completeness", "score": 74, "result": "Review", "detail": "MSME certificate is missing."},
            {"name": "Tax ID verification", "score": 88, "result": "Pass", "detail": "GSTIN format validated."},
            {"name": "Bank verification", "score": 79, "result": "Review", "detail": "Cancelled cheque image quality is low."},
            {"name": "Sanctions screening", "score": 96, "result": "Pass", "detail": "No match found."},
            {"name": "Compliance questionnaire", "score": 64, "result": "Review", "detail": "One safety declaration requires confirmation."},
        ],
    },
    {
        "id": "VO-1003",
        "vendor_name": "BluePeak IT Solutions",
        "category": "IT Services",
        "region": "India",
        "submitted_by": "Technology Team",
        "submitted_at": "2026-10-06T06:05:00+00:00",
        "status": "AUTO_APPROVED",
        "confidence": 89,
        "risk_level": "Low",
        "assigned_to": "Auto Approval Engine",
        "document": "bluepeak-kyc.pdf",
        "extracted_fields": {
            "legal_name": "BluePeak IT Solutions LLP",
            "tax_id": "29AATFB2251M1ZX",
            "pan": "AATFB2251M",
            "bank_account": "XXXXXX6677",
            "ifsc": "KKBK0000421",
            "registered_address": "Bengaluru, Karnataka",
            "contact_email": "finance@bluepeak.example",
        },
        "checks": [
            {"name": "Document completeness", "score": 92, "result": "Pass", "detail": "Core KYC documents attached."},
            {"name": "Tax ID verification", "score": 90, "result": "Pass", "detail": "GSTIN validated."},
            {"name": "Bank verification", "score": 86, "result": "Pass", "detail": "Bank evidence accepted."},
            {"name": "Sanctions screening", "score": 99, "result": "Pass", "detail": "No match found."},
            {"name": "Compliance questionnaire", "score": 78, "result": "Review", "detail": "Security policy acknowledgement is pending."},
        ],
    },
    {
        "id": "VO-1004",
        "vendor_name": "Metro Office Supplies",
        "category": "Office Supplies",
        "region": "India",
        "submitted_by": "Workplace Team",
        "submitted_at": "2026-10-06T06:40:00+00:00",
        "status": "REJECTED",
        "confidence": 52,
        "risk_level": "High",
        "assigned_to": "Vendor Risk Reviewer",
        "document": "metro-office-supplies.pdf",
        "extracted_fields": {
            "legal_name": "Metro Office Supplies",
            "tax_id": "27AAMFM0000A1Z1",
            "pan": "AAMFM0000A",
            "bank_account": "XXXXXX0044",
            "ifsc": "SBIN0000001",
            "registered_address": "Mumbai, Maharashtra",
            "contact_email": "billing@metrooffice.example",
        },
        "checks": [
            {"name": "Document completeness", "score": 58, "result": "Fail", "detail": "Registration proof is unreadable."},
            {"name": "Tax ID verification", "score": 49, "result": "Fail", "detail": "Tax ID failed checksum-style validation."},
            {"name": "Bank verification", "score": 62, "result": "Review", "detail": "Bank document name mismatch."},
            {"name": "Sanctions screening", "score": 91, "result": "Pass", "detail": "No sanctions match found."},
            {"name": "Compliance questionnaire", "score": 38, "result": "Fail", "detail": "Mandatory declarations missing."},
        ],
    },
]


AUDIT_EVENTS: list[dict[str, Any]] = [
    {
        "id": "AUD-0001",
        "case_id": "VO-1001",
        "actor": "System",
        "event_type": "DOCUMENT_UPLOADED",
        "message": "Vendor document received and stored for extraction.",
        "timestamp": "2026-10-06T04:10:16+00:00",
    },
    {
        "id": "AUD-0002",
        "case_id": "VO-1001",
        "actor": "Extraction Agent",
        "event_type": "FIELDS_EXTRACTED",
        "message": "Legal, tax, bank, address, and contact fields auto-populated.",
        "timestamp": "2026-10-06T04:10:28+00:00",
    },
    {
        "id": "AUD-0003",
        "case_id": "VO-1001",
        "actor": "Validation Agent",
        "event_type": "VALIDATION_COMPLETED",
        "message": "Confidence score 94 met threshold 82.",
        "timestamp": "2026-10-06T04:10:44+00:00",
    },
    {
        "id": "AUD-0004",
        "case_id": "VO-1001",
        "actor": "Approval Engine",
        "event_type": "AUTO_APPROVED",
        "message": "Vendor auto-approved because all critical checks passed.",
        "timestamp": "2026-10-06T04:10:48+00:00",
    },
    {
        "id": "AUD-0005",
        "case_id": "VO-1002",
        "actor": "Validation Agent",
        "event_type": "HUMAN_REVIEW_REQUIRED",
        "message": "Confidence score 71 below threshold 82. Routed to reviewer.",
        "timestamp": "2026-10-06T05:26:11+00:00",
    },
]


BASELINE_CASE_EVENTS: list[dict[str, Any]] = [
    {
        "id": "AUD-0006",
        "case_id": "VO-1001",
        "actor": "System",
        "event_type": "INTAKE_SUBMITTED",
        "message": "Initial vendor onboarding request submitted by Procurement Desk.",
        "timestamp": "2026-10-06T04:10:00+00:00",
    },
    {
        "id": "AUD-0007",
        "case_id": "VO-1002",
        "actor": "System",
        "event_type": "INTAKE_SUBMITTED",
        "message": "Initial vendor onboarding request submitted by Admin Team.",
        "timestamp": "2026-10-06T05:25:00+00:00",
    },
    {
        "id": "AUD-0008",
        "case_id": "VO-1002",
        "actor": "Extraction Agent",
        "event_type": "FIELDS_EXTRACTED",
        "message": "Legal, tax, bank, address, and contact fields auto-populated.",
        "timestamp": "2026-10-06T05:25:28+00:00",
    },
    {
        "id": "AUD-0009",
        "case_id": "VO-1002",
        "actor": "Validation Agent",
        "event_type": "VALIDATION_COMPLETED",
        "message": "Confidence score 71 calculated against threshold 82.",
        "timestamp": "2026-10-06T05:25:44+00:00",
    },
    {
        "id": "AUD-0010",
        "case_id": "VO-1003",
        "actor": "System",
        "event_type": "INTAKE_SUBMITTED",
        "message": "Initial vendor onboarding request submitted by Technology Team.",
        "timestamp": "2026-10-06T06:05:00+00:00",
    },
    {
        "id": "AUD-0011",
        "case_id": "VO-1003",
        "actor": "Extraction Agent",
        "event_type": "FIELDS_EXTRACTED",
        "message": "Legal, tax, bank, address, and contact fields auto-populated.",
        "timestamp": "2026-10-06T06:05:28+00:00",
    },
    {
        "id": "AUD-0012",
        "case_id": "VO-1003",
        "actor": "Validation Agent",
        "event_type": "VALIDATION_COMPLETED",
        "message": "Confidence score 89 met threshold 82.",
        "timestamp": "2026-10-06T06:05:44+00:00",
    },
    {
        "id": "AUD-0013",
        "case_id": "VO-1003",
        "actor": "Approval Engine",
        "event_type": "AUTO_APPROVED",
        "message": "Vendor auto-approved because all critical checks passed.",
        "timestamp": "2026-10-06T06:05:48+00:00",
    },
    {
        "id": "AUD-0014",
        "case_id": "VO-1004",
        "actor": "System",
        "event_type": "INTAKE_SUBMITTED",
        "message": "Initial vendor onboarding request submitted by Workplace Team.",
        "timestamp": "2026-10-06T06:40:00+00:00",
    },
    {
        "id": "AUD-0015",
        "case_id": "VO-1004",
        "actor": "Extraction Agent",
        "event_type": "FIELDS_EXTRACTED",
        "message": "Legal, tax, bank, address, and contact fields auto-populated.",
        "timestamp": "2026-10-06T06:40:28+00:00",
    },
    {
        "id": "AUD-0016",
        "case_id": "VO-1004",
        "actor": "Validation Agent",
        "event_type": "VALIDATION_COMPLETED",
        "message": "Confidence score 52 calculated against threshold 82. Critical checks failed.",
        "timestamp": "2026-10-06T06:40:44+00:00",
    },
    {
        "id": "AUD-0017",
        "case_id": "VO-1004",
        "actor": "Approval Engine",
        "event_type": "REJECTED",
        "message": "Case rejected because confidence was below threshold and critical checks failed.",
        "timestamp": "2026-10-06T06:40:48+00:00",
    },
]


def list_cases() -> list[dict[str, Any]]:
    cases = deepcopy(DEMO_CASES)
    for case in cases:
        case.setdefault("submitted_form", {
            **case["extracted_fields"], "category": case["category"],
            "region": case["region"], "submitted_by": case["submitted_by"],
        })
        case.setdefault("documents", [{
            "id": "legacy-document", "name": case["document"],
            "type": "Source document", "available": False,
        }])
    return sorted(cases, key=lambda item: item["submitted_at"], reverse=True)


def find_case(case_id: str) -> dict[str, Any] | None:
    for case in DEMO_CASES:
        if case["id"] == case_id:
            return case
    return None


def list_audit(case_id: str | None = None) -> list[dict[str, Any]]:
    events = deepcopy(AUDIT_EVENTS + BASELINE_CASE_EVENTS)
    if case_id:
        events = [event for event in events if event["case_id"] == case_id]
    return sorted(events, key=lambda item: item["timestamp"], reverse=True)


def add_audit(case_id: str, actor: str, event_type: str, message: str) -> dict[str, Any]:
    event = {
        "id": f"AUD-{len(AUDIT_EVENTS) + len(BASELINE_CASE_EVENTS) + 1:04d}",
        "case_id": case_id,
        "actor": actor,
        "event_type": event_type,
        "message": message,
        "timestamp": utc_now(),
    }
    AUDIT_EVENTS.append(event)
    return deepcopy(event)


def create_case_from_intake(payload: dict[str, Any]) -> dict[str, Any]:
    checks = score_checks(payload)
    decision = route_case(checks, APPROVAL_THRESHOLD)
    case = {
        "id": payload.get("case_id") or f"VO-{1000 + len(DEMO_CASES) + 1}",
        "vendor_name": payload.get("legal_name") or "New Vendor",
        "category": payload.get("category") or "General",
        "region": payload.get("region") or "India",
        "submitted_by": payload.get("submitted_by") or "Portal User",
        "submitted_at": utc_now(),
        "status": decision.status,
        "confidence": decision.confidence,
        "risk_level": decision.risk_level,
        "assigned_to": decision.assigned_to,
        "document": payload.get("document_name") or "uploaded-vendor-document.pdf",
        "extracted_fields": {
            "legal_name": payload.get("legal_name", ""),
            "tax_id": payload.get("tax_id", ""),
            "pan": payload.get("pan", ""),
            "bank_account": payload.get("bank_account", ""),
            "ifsc": payload.get("ifsc", ""),
            "registered_address": payload.get("registered_address", ""),
            "contact_email": payload.get("contact_email", ""),
        },
        "checks": checks,
        "submitted_form": {key: value for key, value in payload.items() if key != "document_name"},
        "documents": [{
            "id": "source-document", "name": payload.get("document_name") or "uploaded-vendor-document.pdf",
            "type": "Source document", "available": False,
        }],
    }
    DEMO_CASES.insert(0, case)
    add_audit(case["id"], "Portal User", "INTAKE_SUBMITTED", "Vendor intake form submitted after document extraction.")
    add_audit(case["id"], "Validation Agent", "VALIDATION_COMPLETED", f"Confidence score {decision.confidence} calculated against threshold {APPROVAL_THRESHOLD}.")
    add_audit(case["id"], "Approval Engine", decision.status, f"Case status set to {decision.status}.")
    return deepcopy(case)
