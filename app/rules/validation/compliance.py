from app.rules.document_fields import DocumentType
from app.rules.validation.common import match_score, text_value
from app.rules.validation.context import ValidationContext
from app.schemas.common import Evidence
from app.schemas.findings import Finding, FindingCode, FindingSeverity


def validate_compliance(ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    supplier_name = (
        ctx.request.legal_name
        or text_value(ctx.field(DocumentType.BUSINESS_REGISTRATION, "legal_name"))
        or text_value(ctx.field(DocumentType.TAX_CERTIFICATE, "legal_name"))
        or ctx.request.supplier_name
    )
    if supplier_name:
        for entry in ctx.sanctions_entries:
            candidates = [entry.name, *entry.aliases]
            matched = max(candidates, key=lambda name: match_score(supplier_name, name))
            score = match_score(supplier_name, matched)
            if score >= ctx.rules_config.sanctions_match_threshold:
                findings.append(
                    Finding(
                        code=FindingCode.SANCTIONS_MATCH,
                        severity=FindingSeverity.BLOCKING,
                        message=f"Supplier name matched synthetic sanctions reference {entry.list_name} at {score}%.",
                        evidence=[
                            Evidence(
                                document_id=f"sanctions:{entry.id}",
                                field_name="matched_name",
                                quote=matched,
                            )
                        ],
                    )
                )

    country = (ctx.request.country or "").strip().casefold()
    high_risk = {item.strip().casefold() for item in ctx.rules_config.high_risk_countries}
    if country and country in high_risk:
        findings.append(
            Finding(
                code=FindingCode.HIGH_RISK_COUNTRY,
                severity=FindingSeverity.WARNING,
                message=f"Request country {ctx.request.country} is in the configured high-risk country set.",
                evidence=[],
            )
        )
    return findings
