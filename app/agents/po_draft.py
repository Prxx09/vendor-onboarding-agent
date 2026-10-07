import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from time import perf_counter

from app.agents.base import BaseAgent
from app.agents.vendor_draft import NormalizedText, _approved_references, _reviewed, _tokens
from app.schemas.common import AgentResult, AgentStatus
from app.schemas.domain import ExtractedFieldRecord
from app.schemas.drafts import PODraft, PODraftInput, PODraftLineItem

CENT = Decimal("0.01")


class PODraftAgent(BaseAgent[PODraftInput, PODraft]):
    """Build a purchase order draft and calculate all money values in Python."""

    name = "po_draft"

    def run(self, input: PODraftInput | dict) -> AgentResult[PODraft]:
        start = perf_counter()
        input = PODraftInput.model_validate(input)
        request = input.request
        fields = input.fields
        approvals = input.approvals
        findings = input.findings
        version = input.version
        warnings = [
            _safe_text(item.message)
            for item in findings
            if item.severity in {"WARNING", "BLOCKING"}
        ]
        line_groups: dict[int, dict[str, ExtractedFieldRecord]] = {}
        for item in fields:
            match = re.fullmatch(r"line_items\[(\d+)\]\.(description|quantity|unit_price|tax)", item.field_name)
            if match and _reviewed(item):
                line_groups.setdefault(int(match.group(1)), {})[match.group(2)] = item
        line_items = []
        subtotal = Decimal(0)
        tax_total = Decimal(0)
        for index in sorted(line_groups):
            values = line_groups[index]
            try:
                description = _value(values.get("description"))
                quantity = _decimal(values.get("quantity"))
                unit_price = _decimal(values.get("unit_price"))
                tax_value = _value(values.get("tax"))
                if not description or quantity is None or unit_price is None or tax_value is None:
                    raise ValueError("incomplete reviewed quotation line")
                tax = _tax_amount(tax_value, quantity * unit_price)
                description = self._normalize_description(description, warnings)
                line_subtotal = (quantity * unit_price).quantize(CENT, rounding=ROUND_HALF_UP)
                tax = tax.quantize(CENT, rounding=ROUND_HALF_UP)
                line_total = line_subtotal + tax
                line_items.append(PODraftLineItem(
                    description=description,
                    quantity=quantity,
                    unit_price=unit_price,
                    tax=tax,
                    line_total=line_total,
                ))
                subtotal += line_subtotal
                tax_total += tax
            except (ValueError, InvalidOperation):
                warnings.append(f"Quotation line {index + 1} was incomplete or invalid and was omitted.")

        subtotal = subtotal.quantize(CENT, rounding=ROUND_HALF_UP)
        tax_total = tax_total.quantize(CENT, rounding=ROUND_HALF_UP)
        total = subtotal + tax_total
        quotation_total = _decimal(_latest(fields, "total"))
        if quotation_total is not None and abs(total - quotation_total) > CENT:
            warnings.append(
                f"Calculated PO total {total} {request.currency or _text(fields, 'currency') or ''} "
                f"differs from quotation total {quotation_total}; neither value was changed."
            )
        if not line_items:
            warnings.append("No complete reviewed quotation line items were available; totals are zero.")

        draft = PODraft(
            request_id=request.id,
            draft_po_reference=f"DRAFT-{request.id.replace('-', '')[:8].upper()}",
            supplier=request.legal_name or request.supplier_name or "Unknown supplier",
            line_items=line_items,
            currency=request.currency or _text(fields, "currency"),
            subtotal=subtotal,
            tax_total=tax_total,
            total=total,
            payment_terms=_text(fields, "payment_terms"),
            delivery_date=_date(_value(_latest(fields, "delivery_date"))),
            approval_references=_approved_references(approvals),
            warnings=warnings,
            version=version,
        )
        return AgentResult(
            agent_name=self.name, status=AgentStatus.OK, data=draft,
            warnings=warnings, duration_ms=self._duration(start),
        )

    def _normalize_description(self, original: str, warnings: list[str]) -> str:
        try:
            result = self.provider.generate_structured(
                system="Normalize spacing and capitalization only. Do not add, remove, or alter facts.",
                user=(
                    "Normalize this quotation line description without changing its words:\n"
                    f"{_mask_prompt(original)}"
                ),
                schema=NormalizedText,
                key="draft_text_normalization",
            )
        except Exception:  # noqa: BLE001 - retain source data on any optional LLM failure
            warnings.append("Line description normalization failed; original quotation text was retained.")
            return original
        candidate = result.normalized_text.strip()
        if _tokens(candidate) != _tokens(original):
            warnings.append("Line description normalization changed source words; original text was retained.")
            return original
        return candidate


def _latest(fields: list[ExtractedFieldRecord], name: str) -> ExtractedFieldRecord | None:
    matches = [item for item in fields if item.field_name == name and _reviewed(item)]
    return max(matches, key=lambda item: item.created_at) if matches else None


def _value(field: ExtractedFieldRecord | None) -> str | None:
    if field is None or field.value is None:
        return None
    return _safe_text(str(field.value))


def _text(fields: list[ExtractedFieldRecord], name: str) -> str | None:
    return _value(_latest(fields, name))


def _safe_text(value: str) -> str:
    from app.services.review_service import _mask_labeled_accounts

    return _mask_labeled_accounts(value)


def _mask_prompt(value: str) -> str:
    from app.services.review_service import _mask_labeled_accounts

    labeled = _mask_labeled_accounts(value)
    return re.sub(
        r"(?<!\d)\d(?:[ -]?\d){7,29}(?!\d)",
        lambda match: f"****{''.join(c for c in match.group(0) if c.isdigit())[-4:]}",
        labeled,
    )


def _decimal(field: ExtractedFieldRecord | None) -> Decimal | None:
    value = _value(field)
    if value is None:
        return None
    return _parse_decimal(value)


def _parse_decimal(value: str) -> Decimal | None:
    cleaned = re.sub(r"[,\s]", "", value)
    cleaned = re.sub(r"^[A-Za-z]{3}", "", cleaned)
    cleaned = cleaned.replace("₹", "").replace("$", "").replace("€", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _tax_amount(value: str, base: Decimal) -> Decimal:
    cleaned = value.strip().replace(",", "")
    if cleaned.endswith("%"):
        rate = Decimal(cleaned[:-1])
        return (base * rate / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
    amount = _parse_decimal(cleaned)
    if amount is None:
        raise ValueError("invalid tax")
    return amount


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


