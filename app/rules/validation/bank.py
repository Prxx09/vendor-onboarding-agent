import re

from app.rules.document_fields import DocumentType
from app.rules.validation.common import finding, raw_bank_account_number, similarity, text_value
from app.rules.validation.context import ValidationContext
from app.schemas.findings import Finding, FindingCode, FindingSeverity

IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$", re.IGNORECASE)
SWIFT_PATTERN = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?$", re.IGNORECASE)
IBAN_PATTERN = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$", re.IGNORECASE)


def iban_is_valid(value: str) -> bool:
    iban = re.sub(r"\s+", "", value).upper()
    if not IBAN_PATTERN.fullmatch(iban):
        return False
    rearranged = iban[4:] + iban[:4]
    expanded = "".join(str(ord(char) - 55) if char.isalpha() else char for char in rearranged)
    remainder = 0
    for digit in expanded:
        remainder = (remainder * 10 + int(digit)) % 97
    return remainder == 1


def validate_bank(ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    bank_type = DocumentType.BANK_DOCUMENT
    routing_field = ctx.field(bank_type, "routing_code")
    routing = text_value(routing_field)
    bank_name_field = ctx.field(bank_type, "bank_name")
    bank_name = text_value(bank_name_field)
    account_field = ctx.field(bank_type, "account_number")
    account = raw_bank_account_number(ctx, account_field)

    if not routing:
        findings.append(
            finding(
                FindingCode.BANK_DETAILS_UNVERIFIABLE,
                FindingSeverity.WARNING,
                "Bank routing code is missing or could not be verified.",
                routing_field,
            )
        )
    else:
        code = re.sub(r"\s+", "", routing).upper()
        bank_entry = None
        code_kind = None
        if IBAN_PATTERN.fullmatch(code):
            if not iban_is_valid(code):
                findings.append(
                    finding(
                        FindingCode.BANK_DETAILS_UNVERIFIABLE,
                        FindingSeverity.WARNING,
                        "IBAN checksum validation failed.",
                        routing_field,
                        mask_account=True,
                    )
                )
        elif IFSC_PATTERN.fullmatch(code):
            code_kind = "ifsc_prefix"
            bank_entry = _bank_by_prefix(ctx, code[:4], code_kind)
        elif SWIFT_PATTERN.fullmatch(code):
            code_kind = "swift_prefix"
            bank_entry = _bank_by_prefix(ctx, code[:4], code_kind)
        else:
            findings.append(
                finding(
                    FindingCode.BANK_DETAILS_UNVERIFIABLE,
                    FindingSeverity.WARNING,
                    "Bank routing code does not match the supported IFSC or SWIFT format.",
                    routing_field,
                )
            )
        if code_kind and bank_entry is None:
            findings.append(
                finding(
                    FindingCode.BANK_DETAILS_UNVERIFIABLE,
                    FindingSeverity.WARNING,
                    "Bank routing code has a valid format but its prefix is not in the local reference.",
                    routing_field,
                )
            )
        elif bank_entry is not None and bank_name and ctx.verification.bank_routing is None and ctx.verification.bank is None:
            expected_name = str(bank_entry["name"])
            if similarity(bank_name, expected_name) < ctx.rules_config.holder_name_similarity_threshold:
                findings.append(
                    finding(
                        FindingCode.BANK_NAME_MISMATCH,
                        FindingSeverity.WARNING,
                        "Bank name does not match the local routing-code reference.",
                        bank_name_field,
                        routing_field,
                    )
                )

    if (
        account
        and IBAN_PATTERN.fullmatch(re.sub(r"\s+", "", account).upper())
        and not iban_is_valid(account)
    ):
        findings.append(
            finding(
                FindingCode.BANK_DETAILS_UNVERIFIABLE,
                FindingSeverity.WARNING,
                "IBAN checksum validation failed.",
                account_field,
                mask_account=True,
            )
        )
    if not account:
        findings.append(
            finding(
                FindingCode.BANK_DETAILS_UNVERIFIABLE,
                FindingSeverity.WARNING,
                "Bank account number is missing or could not be verified.",
                account_field,
                mask_account=True,
            )
        )

    holder_field = ctx.field(bank_type, "account_holder_name")
    holder = text_value(holder_field)
    legal_name = (
        text_value(ctx.field(DocumentType.BUSINESS_REGISTRATION, "legal_name"))
        or text_value(ctx.field(DocumentType.TAX_CERTIFICATE, "legal_name"))
        or ctx.request.legal_name
    )
    if holder and legal_name and ctx.verification.bank is None:
        score = similarity(holder, legal_name)
        if score < ctx.rules_config.holder_name_similarity_threshold:
            findings.append(
                finding(
                    FindingCode.BANK_HOLDER_MISMATCH,
                    FindingSeverity.WARNING,
                    f"Bank account holder similarity to the supplier legal name is {score}%; "
                    f"threshold is {ctx.rules_config.holder_name_similarity_threshold}%.",
                    holder_field,
                    ctx.field(DocumentType.BUSINESS_REGISTRATION, "legal_name")
                    or ctx.field(DocumentType.TAX_CERTIFICATE, "legal_name"),
                )
            )
    return findings


def _bank_by_prefix(ctx: ValidationContext, prefix: str, key: str) -> dict | None:
    return next(
        (bank for bank in ctx.bank_reference.get("banks", []) if bank.get(key, "").upper() == prefix),
        None,
    )


