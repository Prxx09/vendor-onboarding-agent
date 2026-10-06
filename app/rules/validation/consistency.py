from app.rules.document_fields import DocumentType
from app.rules.validation.common import (
    finding,
    normalize_identifier,
    normalize_name,
    similarity,
    text_value,
)
from app.rules.validation.context import ValidationContext
from app.schemas.findings import Finding, FindingCode, FindingSeverity


def validate_consistency(ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    comparisons = (
        ("legal_name", DocumentType.BUSINESS_REGISTRATION, "legal_name", DocumentType.TAX_CERTIFICATE, "legal_name", normalize_name),
        ("address", DocumentType.BUSINESS_REGISTRATION, "address", DocumentType.TAX_CERTIFICATE, "address", normalize_identifier),
        ("tax_id", DocumentType.BUSINESS_REGISTRATION, "tax_id", DocumentType.TAX_CERTIFICATE, "tax_id", normalize_identifier),
    )
    for label, left_type, left_name, right_type, right_name, normalize in comparisons:
        left_field = ctx.field(left_type, left_name)
        right_field = ctx.field(right_type, right_name)
        left = text_value(left_field)
        right = text_value(right_field)
        differs = (
            similarity(left, right) < ctx.rules_config.address_similarity_threshold
            if label == "address" and left and right
            else bool(left and right and normalize(left) != normalize(right))
        )
        if differs:
            findings.append(
                finding(
                    FindingCode.CROSS_DOCUMENT_INCONSISTENCY,
                    FindingSeverity.WARNING,
                    f"{left_type.value}.{left_name} disagrees with "
                    f"{right_type.value}.{right_name} ({label}).",
                    left_field,
                    right_field,
                )
            )

    bank_type = DocumentType.BANK_DOCUMENT
    for field_name in ("legal_name", "address", "tax_id"):
        bank_field = ctx.field(bank_type, field_name)
        if bank_field is None:
            continue
        bank_value = text_value(bank_field)
        if not bank_value:
            continue
        for other_type in (DocumentType.BUSINESS_REGISTRATION, DocumentType.TAX_CERTIFICATE):
            other = ctx.field(other_type, field_name)
            other_value = text_value(other)
            normalize = normalize_name if field_name == "legal_name" else normalize_identifier
            if other_value and normalize(bank_value) != normalize(other_value):
                findings.append(
                    finding(
                        FindingCode.CROSS_DOCUMENT_INCONSISTENCY,
                        FindingSeverity.WARNING,
                        f"{bank_type.value}.{field_name} disagrees with "
                        f"{other_type.value}.{field_name}.",
                        bank_field,
                        other,
                    )
                )
    return findings
