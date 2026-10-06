from app.rules.validation.context import ValidationContext
from app.schemas.common import Evidence
from app.schemas.domain import ExtractedFieldRecord
from app.schemas.findings import Finding, FindingCode, FindingSeverity
from app.utils.masking import mask_account_number


def validate_confidence(ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    for document_type, fields in ctx.extracted_fields.items():
        low_fields = [
            field
            for field in fields
            if field.status.value == "UNVERIFIED"
            or field.confidence is None
            or float(field.confidence) < ctx.rules_config.low_confidence_threshold
        ]
        if not low_fields:
            continue
        evidence: list[Evidence] = []
        names: list[str] = []
        for field in low_fields:
            names.append(field.field_name)
            for raw_evidence in _field_evidence(field):
                quote = raw_evidence.get("quote")
                if quote and ("account" in field.field_name.casefold() or "iban" in field.field_name.casefold()):
                    quote = mask_account_number(quote)
                evidence.append(
                    Evidence(
                        document_id=raw_evidence.get("document_id", field.document_id),
                        field_name=field.field_name,
                        quote=quote or "",
                        page=raw_evidence.get("page"),
                    )
                )
        findings.append(
            Finding(
                code=FindingCode.LOW_CONFIDENCE_FIELD,
                severity=FindingSeverity.WARNING,
                message=(
                    f"{document_type.value} has low-confidence or unverified fields: "
                    f"{', '.join(sorted(set(names)))}."
                ),
                evidence=evidence,
            )
        )
    return findings


def _field_evidence(field: ExtractedFieldRecord):
    evidence = field.evidence
    if isinstance(evidence, list):
        return [item for item in evidence if isinstance(item, dict)]
    if isinstance(evidence, dict):
        return [evidence]
    return []
