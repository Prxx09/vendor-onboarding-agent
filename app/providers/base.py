from abc import ABC, abstractmethod

from app.domain.models import VerificationEvidence


class VerificationProvider(ABC):
    """Stable contract between the agent and verification data sources."""

    @abstractmethod
    async def verify_company(self, registration_number: str) -> VerificationEvidence:
        raise NotImplementedError

    @abstractmethod
    async def verify_tax(self, tax_id: str) -> VerificationEvidence:
        raise NotImplementedError

    @abstractmethod
    async def verify_bank(
        self,
        account_number: str,
        ifsc_swift: str | None,
        expected_account_holder: str | None,
    ) -> VerificationEvidence:
        raise NotImplementedError

    @abstractmethod
    async def verify_kyc(
        self,
        legal_name: str,
        registration_number: str | None,
        tax_id: str | None,
    ) -> VerificationEvidence:
        raise NotImplementedError

    @abstractmethod
    async def check_sanctions(self, legal_name: str) -> VerificationEvidence:
        raise NotImplementedError

    @abstractmethod
    async def check_duplicate_tax_id(self, tax_id: str) -> VerificationEvidence:
        raise NotImplementedError
