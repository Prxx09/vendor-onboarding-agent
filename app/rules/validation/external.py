from app.integrations.base import VerificationMode, VerificationStatus
from app.rules.document_fields import DocumentType
from app.rules.validation.common import evidence_for_field, similarity, text_value
from app.rules.validation.context import ValidationContext
from app.schemas.common import Evidence
from app.schemas.findings import Finding, FindingCode, FindingSeverity


def validate_external(ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    bundle = ctx.verification
    results = [bundle.registry, bundle.tax, bundle.bank, bundle.bank_routing, bundle.sanctions]
    for result in results:
        if result and result.status == VerificationStatus.UNAVAILABLE:
            findings.append(_finding(
                FindingCode.VERIFICATION_UNAVAILABLE, FindingSeverity.BLOCKING,
                result.capability, "Provider could not complete verification.", result.mode,
                [Evidence(document_id=f"verification:{result.capability}", field_name="status",
                          quote=VerificationStatus.UNAVAILABLE.value,
                          verification_mode=result.mode.value)],
            ))

    for label, result in (("company registry", bundle.registry), ("tax identifier", bundle.tax)):
        if not result:
            continue
        failed = result.status in {VerificationStatus.NOT_FOUND, VerificationStatus.MISMATCH}
        if label == "company registry" and result.status == VerificationStatus.VERIFIED:
            failed = result.active is False
        if label == "tax identifier" and result.status == VerificationStatus.VERIFIED:
            failed = bool(result.tax_status and result.tax_status.casefold() in {"inactive", "cancelled", "suspended"})
        if failed:
            findings.append(_finding(
                FindingCode.KYC_VERIFICATION_FAILED, FindingSeverity.BLOCKING,
                result.capability, f"{label.capitalize()} verification did not pass.", result.mode,
                [Evidence(document_id=f"verification:{result.capability}", field_name="status",
                          quote=result.status.value, verification_mode=result.mode.value)],
            ))

    sanctions = bundle.sanctions
    if sanctions:
        for match in sanctions.matches:
            if match.score >= ctx.rules_config.sanctions_match_threshold:
                findings.append(_finding(
                    FindingCode.SANCTIONS_MATCH, FindingSeverity.BLOCKING,
                    "sanctions", f"Supplier matched {match.list_name} at {match.score}%.", sanctions.mode,
                    [Evidence(document_id="verification:sanctions", field_name="matched_name",
                              quote=match.name, verification_mode=sanctions.mode.value)],
                ))

    bank = bundle.bank
    if bank:
        if bank.status in {VerificationStatus.NOT_FOUND, VerificationStatus.MISMATCH} or bank.account_active is False:
            findings.append(_finding(
                FindingCode.BANK_DETAILS_UNVERIFIABLE, FindingSeverity.WARNING,
                "bank_account", "Bank account could not be verified as active.", bank.mode,
                [Evidence(document_id="verification:bank_account", field_name="status",
                          quote=bank.status.value, verification_mode=bank.mode.value)],
            ))
        holder = text_value(ctx.field(DocumentType.BANK_DOCUMENT, "account_holder_name"))
        legal = (ctx.request.legal_name or text_value(
            ctx.field(DocumentType.BUSINESS_REGISTRATION, "legal_name")))
        holder_score = bank.holder_name_match_score
        if holder_score is None and bank.mode == VerificationMode.LOCAL_SIMULATED:
            holder_score = float(similarity(holder, legal))
        if holder_score is not None and holder_score < ctx.rules_config.holder_name_similarity_threshold:
            findings.append(_finding(
                FindingCode.BANK_HOLDER_MISMATCH, FindingSeverity.WARNING,
                "bank_account", f"Bank holder match score {holder_score}% is below threshold.", bank.mode,
                evidence_for_field(ctx.field(DocumentType.BANK_DOCUMENT, "account_holder_name"))
                + [Evidence(document_id="verification:bank_account", field_name="holder_name_match_score",
                            quote=str(holder_score), verification_mode=bank.mode.value)],
            ))
        declared_bank = text_value(ctx.field(DocumentType.BANK_DOCUMENT, "bank_name"))
        resolved_bank = bank.resolved_bank_name
        if resolved_bank and declared_bank and similarity(resolved_bank, declared_bank) < ctx.rules_config.holder_name_similarity_threshold:
            findings.append(_finding(
                FindingCode.BANK_NAME_MISMATCH, FindingSeverity.WARNING,
                "bank_account", "Bank name differs from the provider's resolved bank.", bank.mode,
                evidence_for_field(ctx.field(DocumentType.BANK_DOCUMENT, "bank_name"))
                + [Evidence(document_id="verification:bank_account", field_name="resolved_bank_name",
                            quote=resolved_bank, verification_mode=bank.mode.value)],
            ))
    return findings


def _finding(code, severity, capability, message, mode, evidence):
    label = " (simulated)" if mode == VerificationMode.LOCAL_SIMULATED else ""
    return Finding(code=code, severity=severity, message=f"{message}{label}", evidence=evidence)
