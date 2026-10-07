from dataclasses import dataclass

from app.integrations.bank import BankVerificationResult, RoutingLookupResult
from app.integrations.base import VerificationMode, VerificationStatus
from app.integrations.registry import CompanyVerificationResult
from app.integrations.sanctions import SanctionsResult
from app.integrations.tax import TaxVerificationResult
from app.schemas.domain import VerificationResultRecord


@dataclass
class VerificationBundle:
    registry: CompanyVerificationResult | None = None
    tax: TaxVerificationResult | None = None
    bank: BankVerificationResult | None = None
    bank_routing: RoutingLookupResult | None = None
    sanctions: SanctionsResult | None = None

    @classmethod
    def from_records(cls, records: list[VerificationResultRecord]):
        types = {
            "company_registry": ("registry", CompanyVerificationResult),
            "tax_id": ("tax", TaxVerificationResult),
            "bank_account": ("bank", BankVerificationResult),
            "bank_routing": ("bank_routing", RoutingLookupResult),
            "sanctions": ("sanctions", SanctionsResult),
        }
        bundle = cls()
        for record in records:
            mapped = types.get(record.capability)
            if mapped is None:
                continue
            attribute, result_type = mapped
            values = {
                "capability": record.capability, "provider_name": record.provider_name,
                "mode": VerificationMode(record.mode), "status": VerificationStatus(record.status),
                "checked_at": record.checked_at, "reference_id": record.reference_id,
                "latency_ms": record.latency_ms, "error": record.error,
                "details": {key: val for key, val in record.details.items() if key != "normalized"},
                **record.details.get("normalized", {}),
            }
            setattr(bundle, attribute, result_type.model_validate(values))
        return bundle
