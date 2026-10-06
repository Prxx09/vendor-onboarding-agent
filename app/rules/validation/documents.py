from datetime import datetime

from app.rules.document_fields import DocumentType
from app.rules.validation.common import finding, parse_date, text_value
from app.rules.validation.context import ValidationContext
from app.schemas.findings import Finding, FindingCode, FindingSeverity

REQUIRED_DOCUMENTS = (
    DocumentType.BUSINESS_REGISTRATION,
    DocumentType.TAX_CERTIFICATE,
    DocumentType.BANK_DOCUMENT,
)


def validate_documents(ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    available = {doc.doc_type.upper() for doc in ctx.documents}
    for document_type in REQUIRED_DOCUMENTS:
        if document_type.value not in available:
            findings.append(
                finding(
                    FindingCode.MISSING_REQUIRED_DOCUMENT,
                    FindingSeverity.BLOCKING,
                    f"Required {document_type.value.replace('_', ' ').lower()} document is missing.",
                    document_type=document_type,
                    fallback_quote=f"No {document_type.value} document was provided for request {ctx.request.id}.",
                )
            )

    expiry = ctx.field(DocumentType.BUSINESS_REGISTRATION, "expiry_date")
    expiry_date = parse_date(expiry.value) if expiry and expiry.status.value == "FOUND" else None
    if expiry_date is not None and expiry_date < ctx.today:
        findings.append(
            finding(
                FindingCode.EXPIRED_DOCUMENT,
                FindingSeverity.BLOCKING,
                f"Business registration expired on {expiry_date.isoformat()}.",
                expiry,
                document_type=DocumentType.BUSINESS_REGISTRATION,
            )
        )

    bank_document = ctx.doc(DocumentType.BANK_DOCUMENT)
    if bank_document is not None:
        bank_date_field = ctx.field(DocumentType.BANK_DOCUMENT, "document_date")
        bank_date = parse_date(text_value(bank_date_field)) if bank_date_field else None
        if bank_date is None:
            created_at = bank_document.created_at
            bank_date = created_at.date() if isinstance(created_at, datetime) else created_at
        age_days = (ctx.today - bank_date).days if bank_date else None
        if age_days is not None and age_days > ctx.rules_config.bank_letter_max_age_days:
            findings.append(
                finding(
                    FindingCode.BANK_DETAILS_UNVERIFIABLE,
                    FindingSeverity.WARNING,
                    f"Bank document is {age_days} days old; maximum accepted age is "
                    f"{ctx.rules_config.bank_letter_max_age_days} days.",
                    bank_date_field,
                    document_type=DocumentType.BANK_DOCUMENT,
                    fallback_quote=f"Bank document date: {bank_date.isoformat()}",
                )
            )
    return findings
