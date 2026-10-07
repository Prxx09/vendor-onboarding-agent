import hashlib
import json

from app.integrations.bank import BankVerificationResult
from app.integrations.base import VerificationMode, VerificationStatus
from app.integrations.bundle import VerificationBundle
from app.integrations.factory import VerificationRegistry
from app.integrations.local.sanctions import LocalSanctionsProvider
from app.integrations.registry import CompanyVerificationResult
from app.integrations.sanctions import SanctionsResult
from app.integrations.tax import TaxVerificationResult
from app.repositories.base import OnboardingRepository
from app.rules.document_fields import DocumentType
from app.rules.validation.common import raw_bank_account_number, text_value
from app.rules.validation.context import ValidationContext
from app.schemas.domain import ActorType, AuditEvent, ReviewStatus
from app.workflow.states import WorkflowStatus, can_transition


class VerificationService:
    def __init__(self, repo: OnboardingRepository, registry: VerificationRegistry):
        self.repo = repo
        self.registry = registry

    def run_all(self, request_id: str) -> VerificationBundle:
        request = self.repo.get_request(request_id)
        if request is None:
            raise KeyError(f"Request not found: {request_id}")
        documents = self.repo.list_documents(request_id)
        doc_types = {doc.id: _document_type(doc.doc_type) for doc in documents}
        fields = {}
        for item in self.repo.list_extracted_fields(request_id):
            if item.review_status not in {ReviewStatus.CONFIRMED, ReviewStatus.CORRECTED}:
                continue
            fields.setdefault(doc_types.get(item.document_id, DocumentType.UNKNOWN), []).append(item)
        ctx = ValidationContext(
            request=request, documents=documents, extracted_fields=fields,
            existing_vendors=[], sanctions_entries=[],
        )
        legal_name = (
            text_value(ctx.field(DocumentType.BUSINESS_REGISTRATION, "legal_name"))
            or text_value(ctx.field(DocumentType.TAX_CERTIFICATE, "legal_name")) or ""
        )
        country = request.country or ""
        registration_number = text_value(ctx.field(DocumentType.BUSINESS_REGISTRATION, "registration_number"))
        tax_id = text_value(ctx.field(DocumentType.TAX_CERTIFICATE, "tax_id")) or ""
        account_field = ctx.field(DocumentType.BANK_DOCUMENT, "account_number")
        account_number = raw_bank_account_number(ctx, account_field) or ""
        routing_code = text_value(ctx.field(DocumentType.BANK_DOCUMENT, "routing_code")) or ""
        holder = text_value(ctx.field(DocumentType.BANK_DOCUMENT, "account_holder_name")) or ""
        bank_name = text_value(ctx.field(DocumentType.BANK_DOCUMENT, "bank_name"))
        currency = text_value(ctx.field(DocumentType.BANK_DOCUMENT, "currency"))
        sanctions_provider = self.registry.sanctions
        if isinstance(sanctions_provider, LocalSanctionsProvider):
            sanctions_provider = LocalSanctionsProvider(self.repo.list_sanctions_entries())
        results = VerificationBundle(
            registry=(self.registry.registry.verify_company(registration_number, legal_name, country)
                      if registration_number and legal_name and country else _not_configured("company_registry", CompanyVerificationResult)),
            tax=(self.registry.tax.verify_tax_id(tax_id, country, legal_name)
                 if tax_id and country and legal_name else _not_configured("tax_id", TaxVerificationResult)),
            bank=(self.registry.bank.verify_account(account_number, routing_code, holder, bank_name, country, currency)
                  if account_number and routing_code and holder and country else _not_configured("bank_account", BankVerificationResult)),
            sanctions=sanctions_provider.screen(legal_name, [], country)
            if legal_name and country else _not_configured("sanctions", SanctionsResult),
        )
        records = []
        unavailable = False
        for result, data in (
            (results.registry, {"registration_number": registration_number, "legal_name": legal_name, "country": country}),
            (results.tax, {"tax_id": tax_id, "legal_name": legal_name, "country": country}),
            (results.bank, {"account_number": account_number, "routing_code": routing_code, "holder": holder, "country": country}),
            (results.sanctions, {"legal_name": legal_name, "country": country}),
        ):
            assert result is not None
            input_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            records.append(result.to_record(request_id))
            self.repo.append_audit_event(AuditEvent(
                request_id=request_id, actor="verification_service", actor_type=ActorType.SYSTEM,
                event_type="VERIFICATION_COMPLETED",
                details={"provider": result.provider_name, "capability": result.capability,
                         "status": result.status.value, "latency_ms": result.latency_ms,
                         "input_hash": input_hash},
            ))
            unavailable |= result.status == VerificationStatus.UNAVAILABLE
        self.repo.save_verification_results(request_id, records)
        if unavailable and can_transition(request.status, WorkflowStatus.NEEDS_MANUAL_REVIEW):
            self.repo.set_request_status(
                request_id, WorkflowStatus.NEEDS_MANUAL_REVIEW, "verification_service",
                "An external verification provider was unavailable.",
            )
        return results


def _not_configured(capability, result_type):
    return result_type(
        capability=capability, provider_name="input_gate", mode=VerificationMode.LOCAL_SIMULATED,
        status=VerificationStatus.NOT_CONFIGURED,
        error="Reviewed values required for verification are unavailable.",
    )


def _document_type(value):
    try:
        return DocumentType(value.upper())
    except ValueError:
        return DocumentType.UNKNOWN
