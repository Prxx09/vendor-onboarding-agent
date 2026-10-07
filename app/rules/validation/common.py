import re
from datetime import UTC, date, datetime
from typing import Any

from rapidfuzz.fuzz import ratio

from app.rules.document_fields import DocumentType
from app.rules.validation.context import ValidationContext
from app.schemas.common import Evidence
from app.schemas.domain import ExtractedFieldRecord
from app.schemas.findings import Finding
from app.tools.text_cleaning import normalize_text_for_matching
from app.utils.masking import mask_account_number


def text_value(field: ExtractedFieldRecord | None) -> str | None:
    if field is None or field.value is None or field.status.value != "FOUND":
        return None
    return str(field.value).strip()


def normalize_identifier(value: str | None) -> str:
    return "".join(character for character in (value or "").casefold() if character.isalnum())


def raw_bank_account_number(
    ctx: ValidationContext, account_field: ExtractedFieldRecord | None
) -> str | None:
    value = text_value(account_field)
    if value and not value.startswith("****"):
        return value
    document = ctx.doc(DocumentType.BANK_DOCUMENT)
    if document is None or not document.text_content:
        return value
    match = re.search(
        r"(?i)\b(?:account\s*(?:number|no\.?|#)|a/c\s*(?:number|no\.?|#)|iban)\s*[:#-]?\s*"
        r"((?:\d[ -]?){5,30}\d|[A-Z0-9][A-Z0-9-]{7,33})",
        document.text_content,
    )
    return match.group(1).strip().rstrip(" .,:;") if match else value


def normalize_name(value: str | None) -> str:
    text = normalize_text_for_matching(value or "")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    suffixes = {"pvt", "private", "ltd", "limited", "llc", "inc", "corp", "co"}
    tokens = [token for token in text.split() if token not in suffixes]
    return " ".join(tokens)


def similarity(left: str | None, right: str | None) -> int:
    if not left or not right:
        return 0
    return round(ratio(normalize_name(left), normalize_name(right)))


def evidence_for_field(
    field: ExtractedFieldRecord | None,
    *,
    document_type: DocumentType | None = None,
    fallback_quote: str | None = None,
    mask_account: bool = False,
) -> list[Evidence]:
    if field is None:
        return []
    document_id = field.document_id
    field_name = field.field_name
    evidence = field.evidence
    quote = evidence.get("quote") if isinstance(evidence, dict) else None
    if isinstance(evidence, list) and evidence:
        first = evidence[0]
        quote = first.get("quote") if isinstance(first, dict) else None
    if not quote:
        return []
    if mask_account or "account" in field_name.casefold() or "iban" in field_name.casefold():
        quote = mask_account_number(str(quote)) if quote is not None else None
    return [Evidence(document_id=document_id, field_name=field_name, quote=quote or "")]


def finding(
    code: str,
    severity: str,
    message: str,
    *fields: ExtractedFieldRecord | None,
    document_type: DocumentType | None = None,
    fallback_quote: str | None = None,
    mask_account: bool = False,
    related_vendor_id: str | None = None,
) -> Finding:
    evidence: list[Evidence] = []
    for item in fields:
        evidence.extend(evidence_for_field(item, mask_account=mask_account))
    if not evidence and (fallback_quote is not None or document_type is not None):
        evidence = evidence_for_field(
            None,
            document_type=document_type,
            fallback_quote=fallback_quote,
            mask_account=mask_account,
        )
    return Finding(
        code=code,
        severity=severity,
        message=message,
        evidence=evidence,
        related_vendor_id=related_vendor_id,
    )


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    for fmt in (
        "%Y-%m-%d", "%Y/%m/%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y",
        "%b %d, %Y", "%d/%m/%Y", "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(candidate, fmt).replace(tzinfo=UTC).date()
        except ValueError:
            continue
    try:
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        return datetime.fromisoformat(candidate).date()
    except ValueError:
        return None


def evidence_ref(evidence: Evidence) -> str:
    return f"{evidence.document_id}:{evidence.field_name}"


def match_score(left: str, right: str) -> int:
    return round(ratio(normalize_text_for_matching(left), normalize_text_for_matching(right)))
