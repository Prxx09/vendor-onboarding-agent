from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


APPROVAL_THRESHOLD = 82


@dataclass(frozen=True)
class RoutingDecision:
    status: str
    assigned_to: str
    risk_level: str
    confidence: int


def simulate_document_extraction(filename: str, category: str) -> dict[str, Any]:
    stem = Path(filename).stem.replace("_", " ").replace("-", " ").title()
    token = "".join(ch for ch in stem.upper() if ch.isalnum())[:5].ljust(5, "X")
    return {
        "document_name": filename,
        "category": category,
        "extracted_fields": {
            "legal_name": stem or "Sample Vendor Pvt Ltd",
            "tax_id": f"27{token}4587Q1Z3",
            "pan": f"{token}4587Q"[:10],
            "bank_account": "XXXXXX2381",
            "ifsc": "HDFC0001342",
            "registered_address": "Noida, Uttar Pradesh",
            "contact_email": f"accounts@{token.lower()}.example",
        },
        "message": "Demo extraction completed. Please review editable fields before submit.",
    }


def score_checks(fields: dict[str, Any]) -> list[dict[str, Any]]:
    legal_name = str(fields.get("legal_name", "")).strip()
    tax_id = str(fields.get("tax_id", "")).strip()
    pan = str(fields.get("pan", "")).strip()
    bank_account = str(fields.get("bank_account", "")).strip()
    ifsc = str(fields.get("ifsc", "")).strip()
    address = str(fields.get("registered_address", "")).strip()
    email = str(fields.get("contact_email", "")).strip()
    required_fields_present = all([legal_name, tax_id, pan, bank_account, ifsc, address, email])
    tax_format_valid = len(tax_id) >= 12 and len(pan) == 10
    bank_format_valid = len(bank_account) >= 6 and len(ifsc) == 11
    sanctions_hit = "metro" in legal_name.lower()
    compliance_confirmed = bool(fields.get("compliance_confirmed", True))

    return [
        {
            "name": "Document completeness",
            "code": "DOCUMENT_COMPLETENESS",
            "score": 96 if required_fields_present else 62,
            "result": "Pass" if required_fields_present else "Review",
            "detail": "Required fields are present." if required_fields_present else "One or more required fields are missing.",
        },
        {
            "name": "Tax ID verification",
            "code": "TAX_ID_VERIFICATION",
            "score": 92 if tax_format_valid else 48,
            "result": "Pass" if tax_format_valid else "Fail",
            "detail": "Tax identifiers match expected Indian vendor formats." if tax_format_valid else "Tax identifiers need manual verification.",
        },
        {
            "name": "Bank verification",
            "code": "BANK_VERIFICATION",
            "score": 88 if bank_format_valid else 55,
            "result": "Pass" if bank_format_valid else "Review",
            "detail": "Bank account evidence is structurally valid." if bank_format_valid else "Bank account or IFSC format needs review.",
        },
        {
            "name": "Sanctions screening",
            "code": "SANCTIONS_SCREENING",
            "score": 46 if sanctions_hit else 97,
            "result": "Fail" if sanctions_hit else "Pass",
            "detail": "Potential fuzzy match detected." if sanctions_hit else "No sanctions or exclusion match found.",
        },
        {
            "name": "Compliance questionnaire",
            "code": "COMPLIANCE_QUESTIONNAIRE",
            "score": 84 if compliance_confirmed else 41,
            "result": "Pass" if compliance_confirmed else "Fail",
            "detail": "Declarations are accepted." if compliance_confirmed else "Mandatory declarations were not accepted.",
        },
    ]


def calculate_confidence(checks: list[dict[str, Any]]) -> int:
    if not checks:
        return 0
    return round(sum(check["score"] for check in checks) / len(checks))


def route_case(checks: list[dict[str, Any]], threshold: int = APPROVAL_THRESHOLD) -> RoutingDecision:
    confidence = calculate_confidence(checks)
    has_failed_critical_check = any(check["result"] == "Fail" for check in checks)
    status = "AUTO_APPROVED" if confidence >= threshold and not has_failed_critical_check else "HUMAN_REVIEW"
    risk_level = "Low" if confidence >= 88 else "Medium" if confidence >= 65 else "High"
    assigned_to = "Auto Approval Engine" if status == "AUTO_APPROVED" else "Vendor Risk Reviewer"
    return RoutingDecision(
        status=status,
        assigned_to=assigned_to,
        risk_level=risk_level,
        confidence=confidence,
    )
