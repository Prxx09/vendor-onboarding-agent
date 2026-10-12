import httpx

from app.core.config import get_settings
from app.domain.models import VerificationEvidence
from app.providers.base import VerificationProvider


class HttpVerificationProvider(VerificationProvider):
    """Adapter for future official/company/KYC/bank services."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=20.0)

    def _headers(self) -> dict[str, str]:
        if not self.settings.OFFICIAL_API_KEY:
            return {}
        value = self.settings.OFFICIAL_API_KEY
        if (
            self.settings.OFFICIAL_API_KEY_HEADER.lower() == "authorization"
            and not value.lower().startswith("bearer ")
        ):
            value = f"Bearer {value}"
        return {self.settings.OFFICIAL_API_KEY_HEADER: value}

    async def _call(self, url: str | None, payload: dict) -> dict:
        if not url:
            raise RuntimeError("Verification API endpoint is not configured.")
        response = await self.client.post(url, json=payload, headers=self._headers())
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _normalize(source: str, raw: dict) -> VerificationEvidence:
        if raw.get("review_required"):
            status = "REVIEW_REQUIRED"
        elif raw.get("verified"):
            status = "VERIFIED"
        elif raw.get("found") is False:
            status = "NOT_FOUND"
        else:
            status = "ERROR"

        return VerificationEvidence(
            source=source,
            status=status,
            message=raw.get("message", "Verification provider response received."),
            data=raw.get("data", raw),
        )

    async def verify_company(self, registration_number: str) -> VerificationEvidence:
        raw = await self._call(
            self.settings.COMPANY_REGISTRY_API_URL,
            {"registration_number": registration_number},
        )
        return self._normalize("company_registry_api", raw)

    async def verify_tax(self, tax_id: str) -> VerificationEvidence:
        raw = await self._call(self.settings.TAX_REGISTRY_API_URL, {"tax_id": tax_id})
        return self._normalize("tax_registry_api", raw)

    async def verify_bank(
        self,
        account_number: str,
        ifsc_swift: str | None,
        expected_account_holder: str | None,
    ) -> VerificationEvidence:
        raw = await self._call(
            self.settings.BANK_VERIFICATION_API_URL,
            {
                "account_number": account_number,
                "ifsc_swift": ifsc_swift,
                "expected_account_holder": expected_account_holder,
            },
        )
        return self._normalize("bank_verification_api", raw)

    async def verify_kyc(
        self,
        legal_name: str,
        registration_number: str | None,
        tax_id: str | None,
    ) -> VerificationEvidence:
        raw = await self._call(
            self.settings.KYC_API_URL,
            {
                "legal_name": legal_name,
                "registration_number": registration_number,
                "tax_id": tax_id,
            },
        )
        return self._normalize("kyc_api", raw)

    async def check_sanctions(self, legal_name: str) -> VerificationEvidence:
        raw = await self._call(
            self.settings.SANCTIONS_API_URL,
            {"legal_name": legal_name},
        )
        return self._normalize("sanctions_api", raw)

    async def check_duplicate_tax_id(self, tax_id: str) -> VerificationEvidence:
        raw = await self._call(
            self.settings.TAX_REGISTRY_API_URL,
            {"operation": "duplicate_vendor_check", "tax_id": tax_id},
        )
        return self._normalize("vendor_master_api", raw)
