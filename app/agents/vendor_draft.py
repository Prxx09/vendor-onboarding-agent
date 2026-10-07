import re
from time import perf_counter

from pydantic import BaseModel, ConfigDict

from app.agents.base import BaseAgent
from app.schemas.common import AgentResult, AgentStatus
from app.schemas.domain import (
    Approval,
    ApprovalDecision,
    ExtractedFieldRecord,
    ReviewStatus,
)
from app.schemas.drafts import (
    DraftVerificationStatus,
    SourceFieldReference,
    VendorBankDraft,
    VendorDraft,
    VendorDraftInput,
)
from app.utils.masking import mask_account_number


class NormalizedText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalized_text: str


class VendorDraftAgent(BaseAgent[VendorDraftInput, VendorDraft]):
    """Assemble a vendor draft from persisted facts; optional LLM use is text-only."""

    name = "vendor_draft"

    def run(self, input: VendorDraftInput | dict) -> AgentResult[VendorDraft]:
        start = perf_counter()
        input = VendorDraftInput.model_validate(input)
        request = input.request
        fields = input.fields
        verifications = input.verifications
        approvals = input.approvals
        findings = input.findings
        version = input.version
        approved = _approved_references(approvals)
        warnings = [
            _safe_text(item.message)
            for item in findings
            if item.severity in {"WARNING", "BLOCKING"}
        ]
        local_checks = [item.capability for item in verifications if item.mode == "LOCAL_SIMULATED"]
        if local_checks:
            warnings.append(
                "Verification used LOCAL_SIMULATED checks and does not represent live external confirmation: "
                + ", ".join(sorted(set(local_checks)))
                + "."
            )

        legal_name = _text(_field(fields, "legal_name")) or request.legal_name or request.supplier_name
        address = _text(_field(fields, "address")) or request.address
        if address:
            normalized = self._normalize(address)
            if normalized is None:
                warnings.append("Address normalization was unavailable; original extracted address was retained.")
            else:
                address = normalized
        account = _text(_field(fields, "account_number"))
        bank = VendorBankDraft(
            bank_name=_text(_field(fields, "bank_name")),
            branch=_text(_field(fields, "branch")),
            account_number_masked=mask_account_number(account) if account else None,
            routing_code=_text(_field(fields, "routing_code")),
            currency=_text(_field(fields, "currency")) or request.currency,
        )
        field_names = (
            "legal_name", "trading_name", "tax_id", "registration_number", "address",
            "country", "company_type", "contact", "contact_person", "email", "phone",
            "bank_name", "branch", "account_number", "routing_code", "currency", "payment_terms",
        )
        references = [
            SourceFieldReference(
                document_id=item.document_id, field_id=item.id, field_name=item.field_name
            )
            for item in fields
            if item.field_name in field_names and _reviewed(item)
        ]
        draft = VendorDraft(
            request_id=request.id,
            legal_name=legal_name,
            trading_name=_text(_field(fields, "trading_name"))
            or (request.supplier_name if request.supplier_name != legal_name else None),
            tax_id=_text(_field(fields, "tax_id")) or request.tax_id,
            registration_number=_text(_field(fields, "registration_number")),
            address=address,
            country=request.country or _text(_field(fields, "country")),
            supplier_category=_text(_field(fields, "company_type")),
            contact=(
                _text(_field(fields, "contact"))
                or _text(_field(fields, "contact_person"))
                or _text(_field(fields, "email"))
                or _text(_field(fields, "phone"))
            ),
            bank=bank,
            payment_terms=_text(_field(fields, "payment_terms")),
            approval_references=approved,
            source_field_references=references,
            verification_status=[
                DraftVerificationStatus(
                    capability=item.capability,
                    provider=item.provider_name,
                    mode=item.mode,
                    status=item.status,
                )
                for item in verifications
            ],
            warnings=warnings,
            version=version,
        )
        return AgentResult(
            agent_name=self.name, status=AgentStatus.OK, data=draft,
            warnings=warnings, duration_ms=self._duration(start),
        )

    def _normalize(self, original: str) -> str | None:
        try:
            result = self.provider.generate_structured(
                system="Normalize spacing and capitalization only. Do not add, remove, or alter facts.",
                user=f"Normalize this address without changing its words:\n{_mask_prompt(original)}",
                schema=NormalizedText,
                key="draft_text_normalization",
            )
        except Exception:  # noqa: BLE001 - LLM is optional; retain source on any failure
            return None
        candidate = result.normalized_text.strip()
        if _tokens(candidate) != _tokens(original):
            return None
        return candidate


def _field(fields: list[ExtractedFieldRecord], name: str) -> ExtractedFieldRecord | None:
    matches = [item for item in fields if item.field_name == name and _reviewed(item)]
    return max(matches, key=lambda item: item.created_at) if matches else None


def _reviewed(field: ExtractedFieldRecord) -> bool:
    return field.review_status in {ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED}


def _text(field: ExtractedFieldRecord | None) -> str | None:
    if field is None or field.value is None:
        return None
    return _safe_text(str(field.value))


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


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[\w]+", value.casefold()))


def _approved_references(approvals: list[Approval]) -> list[str]:
    return [
        item.id for item in sorted(approvals, key=lambda item: item.created_at)
        if item.decision == ApprovalDecision.APPROVE
    ]
