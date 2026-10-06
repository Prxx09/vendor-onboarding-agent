import re

from app.rules.document_fields import DocumentType
from app.rules.validation.common import (
    evidence_for_field,
    finding,
    normalize_identifier,
    raw_bank_account_number,
    similarity,
    text_value,
)
from app.rules.validation.context import ValidationContext
from app.schemas.common import Evidence
from app.schemas.findings import Finding, FindingCode, FindingSeverity
from app.utils.masking import mask_account_number

TAX_ID_PATTERNS: dict[str, str] = {
    "IN": r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$",
    "INDIA": r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$",
}


def validate_supplier(ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    tax_field = ctx.field(DocumentType.TAX_CERTIFICATE, "tax_id")
    tax_id = ctx.request.tax_id or text_value(tax_field)
    country = (ctx.request.country or "").strip().upper()
    pattern = TAX_ID_PATTERNS.get(country)
    if tax_id and pattern and re.fullmatch(pattern, tax_id.strip().upper()) is None:
        findings.append(
            finding(
                FindingCode.INVALID_TAX_ID_FORMAT,
                FindingSeverity.WARNING,
                f"Tax identifier does not match the configured format for {country}.",
                tax_field,
                document_type=DocumentType.TAX_CERTIFICATE,
                fallback_quote=f"Tax ID format checked for country {country}.",
            )
        )

    if tax_id:
        normalized_tax = normalize_identifier(tax_id)
        for vendor in ctx.existing_vendors:
            if normalized_tax and normalized_tax == normalize_identifier(vendor.tax_id):
                evidence = evidence_for_field(tax_field)
                evidence.append(
                    Evidence(
                        document_id=f"vendor:{vendor.id}",
                        field_name="tax_id",
                        quote=f"Existing vendor tax identifier: {vendor.tax_id}",
                    )
                )
                findings.append(
                    Finding(
                        code=FindingCode.DUPLICATE_TAX_ID,
                        severity=FindingSeverity.BLOCKING,
                        message=f"Tax identifier matches existing vendor {vendor.legal_name}.",
                        evidence=evidence,
                        related_vendor_id=vendor.id,
                    )
                )

    candidate_name = (
        ctx.request.legal_name
        or text_value(ctx.field(DocumentType.BUSINESS_REGISTRATION, "legal_name"))
        or text_value(ctx.field(DocumentType.TAX_CERTIFICATE, "legal_name"))
        or ctx.request.supplier_name
    )
    for vendor in ctx.existing_vendors:
        if tax_id and normalize_identifier(tax_id) == normalize_identifier(vendor.tax_id):
            continue
        score = similarity(candidate_name, vendor.legal_name)
        if score >= ctx.rules_config.name_similarity_threshold:
            findings.append(
                Finding(
                    code=FindingCode.SIMILAR_SUPPLIER_NAME,
                    severity=FindingSeverity.WARNING,
                    message=(
                        f"Supplier name is {score}% similar to existing vendor "
                        f"{vendor.legal_name} (threshold {ctx.rules_config.name_similarity_threshold}%)."
                    ),
                    evidence=[
                        *evidence_for_field(ctx.field(DocumentType.BUSINESS_REGISTRATION, "legal_name")),
                        Evidence(
                            document_id=f"vendor:{vendor.id}",
                            field_name="legal_name",
                            quote=f"Existing vendor legal name: {vendor.legal_name}",
                        ),
                    ],
                    related_vendor_id=vendor.id,
                )
            )

    account_field = ctx.field(DocumentType.BANK_DOCUMENT, "account_number")
    account_number = raw_bank_account_number(ctx, account_field)
    if account_number:
        normalized_account = normalize_identifier(account_number)
        for vendor in ctx.existing_vendors:
            if normalized_account and normalized_account == normalize_identifier(vendor.bank_account_number):
                evidence = evidence_for_field(account_field, mask_account=True)
                evidence.append(
                    Evidence(
                        document_id=f"vendor:{vendor.id}",
                        field_name="bank_account_number",
                        quote=f"Existing account ending {mask_account_number(vendor.bank_account_number)[-4:]}",
                    )
                )
                findings.append(
                    Finding(
                        code=FindingCode.DUPLICATE_BANK_ACCOUNT,
                        severity=FindingSeverity.BLOCKING,
                        message=f"Bank account matches an existing vendor: {vendor.legal_name}.",
                        evidence=evidence,
                        related_vendor_id=vendor.id,
                    )
                )
    return findings
