import re
from hashlib import sha256
from time import perf_counter

from app.integrations.base import VerificationMode, VerificationStatus
from app.integrations.tax import TaxVerificationResult
from app.rules.validation.supplier import TAX_ID_PATTERNS


class LocalTaxProvider:
    provider_name = "local_tax_format_simulation"

    def verify_tax_id(self, tax_id: str, country: str, legal_name: str):
        start = perf_counter()
        pattern = TAX_ID_PATTERNS.get(country.strip().upper())
        valid = bool(pattern and re.fullmatch(pattern, tax_id.strip().upper()))
        status = VerificationStatus.NOT_CONFIGURED if pattern is None else (
            VerificationStatus.VERIFIED if valid else VerificationStatus.MISMATCH
        )
        return TaxVerificationResult(
            capability="tax_id", provider_name=self.provider_name,
            mode=VerificationMode.LOCAL_SIMULATED, status=status,
            latency_ms=round((perf_counter() - start) * 1000),
            reference_id=sha256(tax_id.encode()).hexdigest()[:16],
            registered_legal_name=legal_name if valid else None,
            tax_status="FORMAT_VALID" if valid else None,
            details={"simulation": "format_only_no_government_lookup"},
        )
