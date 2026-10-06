from collections.abc import Callable

from app.rules.validation.bank import validate_bank
from app.rules.validation.compliance import validate_compliance
from app.rules.validation.confidence import validate_confidence
from app.rules.validation.consistency import validate_consistency
from app.rules.validation.context import ValidationContext
from app.rules.validation.documents import validate_documents
from app.rules.validation.purchase import validate_purchase
from app.rules.validation.supplier import validate_supplier
from app.schemas.findings import Finding

VALIDATORS: tuple[Callable[[ValidationContext], list[Finding]], ...] = (
    validate_documents,
    validate_supplier,
    validate_bank,
    validate_consistency,
    validate_compliance,
    validate_purchase,
    validate_confidence,
)


def run_validations(ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    for validator in VALIDATORS:
        findings.extend(validator(ctx))
    return findings
