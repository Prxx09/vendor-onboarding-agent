import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from app.integrations.base import VerificationMode, VerificationStatus
from app.integrations.registry import CompanyVerificationResult
from app.rules.validation.common import similarity

_REGISTRY_FILE = Path(__file__).resolve().parents[3] / "data" / "reference" / "kyc_registry.json"
with _REGISTRY_FILE.open(encoding="utf-8") as handle:
    _COMPANIES = json.load(handle)["companies"]


class LocalRegistryProvider:
    provider_name = "fictional_local_registry"

    def verify_company(self, registration_number: str, legal_name: str, country: str):
        start = perf_counter()
        record = next((
            row for row in _COMPANIES
            if row["registration_number"].casefold() == registration_number.casefold()
            and row["country"].casefold() == country.casefold()
        ), None)
        score = float(similarity(legal_name, record["registered_name"])) if record else None
        status = (
            VerificationStatus.NOT_FOUND if record is None else
            VerificationStatus.VERIFIED if score >= 90 and record["active"] else
            VerificationStatus.MISMATCH
        )
        return CompanyVerificationResult(
            capability="company_registry", provider_name=self.provider_name,
            mode=VerificationMode.LOCAL_SIMULATED, status=status,
            latency_ms=round((perf_counter() - start) * 1000),
            reference_id=sha256(registration_number.encode()).hexdigest()[:16],
            registered_name=record["registered_name"] if record else None,
            active=record["active"] if record else None,
            incorporation_date=record["incorporation_date"] if record else None,
            registered_address=record["registered_address"] if record else None,
            name_match_score=score,
            details={"simulation": "fictional_registry_fixture"},
        )
