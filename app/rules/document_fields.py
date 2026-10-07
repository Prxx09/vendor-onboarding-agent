from enum import StrEnum


class DocumentType(StrEnum):
    BUSINESS_REGISTRATION = "BUSINESS_REGISTRATION"
    TAX_CERTIFICATE = "TAX_CERTIFICATE"
    BANK_DOCUMENT = "BANK_DOCUMENT"
    QUOTATION = "QUOTATION"
    UNKNOWN = "UNKNOWN"


REQUIRED_FIELDS: dict[DocumentType, tuple[str, ...]] = {
    DocumentType.BUSINESS_REGISTRATION: (
        "legal_name", "registration_number", "company_type", "address", "issue_date"
    ),
    DocumentType.TAX_CERTIFICATE: ("tax_id", "legal_name", "address", "tax_status", "effective_date"),
    DocumentType.BANK_DOCUMENT: (
        "account_holder_name", "bank_name", "account_number", "routing_code", "currency"
    ),
    DocumentType.QUOTATION: ("supplier_name", "currency", "total", "payment_terms", "line_items"),
    DocumentType.UNKNOWN: (),
}

OPTIONAL_FIELDS: dict[DocumentType, tuple[str, ...]] = {
    DocumentType.BUSINESS_REGISTRATION: ("expiry_date", "issuing_authority"),
    DocumentType.TAX_CERTIFICATE: (),
    DocumentType.BANK_DOCUMENT: ("branch", "document_date"),
    DocumentType.QUOTATION: ("delivery_date",),
    DocumentType.UNKNOWN: (),
}

LINE_ITEM_FIELDS: tuple[str, ...] = ("description", "quantity", "unit_price", "tax")

FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "legal_name": ("legal name", "company name", "registered name"),
    "registration_number": ("registration number", "company number", "cin"),
    "company_type": ("company type", "entity type"),
    "address": ("registered address", "address"),
    "issue_date": ("issue date", "issued on"),
    "expiry_date": ("expiry date", "expires on"),
    "issuing_authority": ("issuing authority", "issued by"),
    "tax_id": ("tax id", "tax identification", "gstin", "vat number", "pan"),
    "tax_status": ("tax status", "status"),
    "effective_date": ("effective date", "valid from"),
    "account_holder_name": ("account holder", "account name", "beneficiary"),
    "bank_name": ("bank name", "bank"),
    "branch": ("branch",),
    "account_number": ("account number", "account no", "a/c number"),
    "routing_code": ("ifsc", "swift", "routing code", "routing number"),
    "currency": ("currency",),
    "document_date": ("document date", "statement date"),
    "supplier_name": ("supplier name", "vendor name", "seller"),
    "total": ("total", "grand total", "amount due"),
    "payment_terms": ("payment terms", "payment due"),
    "delivery_date": ("delivery date", "deliver by"),
}


def fields_for(document_type: DocumentType) -> tuple[str, ...]:
    return REQUIRED_FIELDS[document_type] + OPTIONAL_FIELDS[document_type]


def field_specification(document_type: DocumentType | None) -> str:
    types = [document_type] if document_type and document_type != DocumentType.UNKNOWN else [
        DocumentType.BUSINESS_REGISTRATION,
        DocumentType.TAX_CERTIFICATE,
        DocumentType.BANK_DOCUMENT,
        DocumentType.QUOTATION,
    ]
    lines: list[str] = []
    for kind in types:
        required = ", ".join(REQUIRED_FIELDS[kind]) or "none"
        optional = ", ".join(OPTIONAL_FIELDS[kind]) or "none"
        lines.append(f"{kind.value}: required [{required}]; optional [{optional}]")
        if kind == DocumentType.QUOTATION:
            lines.append(f"  line_items: list of {', '.join(LINE_ITEM_FIELDS)}")
    return "\n".join(lines)
