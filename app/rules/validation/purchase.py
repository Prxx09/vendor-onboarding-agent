from app.rules.document_fields import DocumentType
from app.rules.validation.common import finding
from app.rules.validation.context import ValidationContext
from app.schemas.domain import RequestType
from app.schemas.findings import Finding, FindingCode, FindingSeverity


def validate_purchase(ctx: ValidationContext) -> list[Finding]:
    if ctx.request.request_type != RequestType.SUPPLIER_WITH_PURCHASE:
        return []
    findings: list[Finding] = []
    spend = ctx.request.estimated_annual_spend
    if spend is not None and spend >= ctx.rules_config.high_value_threshold:
        findings.append(
            finding(
                FindingCode.HIGH_VALUE_PURCHASE,
                FindingSeverity.WARNING,
                f"Estimated annual spend meets or exceeds the high-value threshold of "
                f"{ctx.rules_config.high_value_threshold}.",
            )
        )
    if not ctx.request.budget_owner_id:
        findings.append(
            finding(
                FindingCode.MISSING_BUDGET_OWNER,
                FindingSeverity.WARNING,
                "Purchase request has no budget owner assigned.",
            )
        )
    if ctx.doc(DocumentType.QUOTATION) is None:
        findings.append(
            finding(
                FindingCode.QUOTATION_REQUIRED,
                FindingSeverity.BLOCKING,
                "A quotation is required for supplier requests with a purchase.",
            )
        )
    return findings
