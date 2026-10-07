from typing import Any

from app.config import get_settings
from app.schemas.common import Evidence
from app.schemas.extraction import ExtractedField, ExtractedFieldStatus
from app.tools.text_cleaning import normalize_text_for_matching

LOW_CONFIDENCE_THRESHOLD = 0.7


def evaluate_extracted_field(
    *,
    document_id: str,
    name: str,
    value: Any,
    evidence_quote: str | None,
    source_text: str,
    threshold: float | None = None,
) -> ExtractedField:
    threshold = get_settings().low_confidence_threshold if threshold is None else threshold
    if value is None or (isinstance(value, str) and not value.strip()):
        return ExtractedField(
            name=name,
            value=None,
            status=ExtractedFieldStatus.MISSING,
            confidence=0.0,
            evidence=None,
            needs_review=True,
        )

    normalized_value = normalize_text_for_matching(value)
    normalized_source = normalize_text_for_matching(source_text)
    normalized_quote = normalize_text_for_matching(evidence_quote) if evidence_quote else ""
    value_in_source = bool(normalized_value) and normalized_value in normalized_source
    quote_in_source = bool(normalized_quote) and normalized_quote in normalized_source
    value_in_quote = bool(normalized_value) and normalized_value in normalized_quote

    if value_in_source and quote_in_source and value_in_quote:
        status, confidence, needs_review = ExtractedFieldStatus.FOUND, 1.0, False
    elif value_in_source:
        status, confidence = ExtractedFieldStatus.FOUND, 0.7
        needs_review = confidence < threshold
    else:
        status, confidence, needs_review = ExtractedFieldStatus.UNVERIFIED, 0.0, True

    evidence_quote_to_use = evidence_quote if quote_in_source else None
    if evidence_quote_to_use is None and value_in_source:
        evidence_quote_to_use = next(
            (
                line.strip()
                for line in source_text.splitlines()
                if normalized_value in normalize_text_for_matching(line)
            ),
            None,
        )
    evidence = (
        Evidence(document_id=document_id, field_name=name, quote=evidence_quote_to_use)
        if evidence_quote_to_use
        else None
    )
    return ExtractedField(
        name=name,
        value=value,
        status=status,
        confidence=confidence,
        evidence=evidence,
        needs_review=needs_review,
    )
