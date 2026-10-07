from hashlib import sha256
from time import perf_counter

from app.integrations.bank import BankVerificationResult, RoutingLookupResult
from app.integrations.base import VerificationMode, VerificationStatus
from app.rules.validation.bank import IFSC_PATTERN, SWIFT_PATTERN, iban_is_valid
from app.rules.validation.context import BANK_REFERENCE


class LocalBankProvider:
    provider_name = "local_bank_reference_simulation"

    @staticmethod
    def _bank(routing_code: str):
        code = "".join(routing_code.split()).upper()
        if IFSC_PATTERN.fullmatch(code):
            kind = "ifsc_prefix"
        elif SWIFT_PATTERN.fullmatch(code):
            kind = "swift_prefix"
        else:
            return None
        return next((row for row in BANK_REFERENCE.get("banks", []) if row.get(kind) == code[:4]), None)

    def lookup_routing_code(self, routing_code: str):
        start = perf_counter()
        bank = self._bank(routing_code)
        return RoutingLookupResult(
            capability="bank_routing", provider_name=self.provider_name,
            mode=VerificationMode.LOCAL_SIMULATED,
            status=VerificationStatus.VERIFIED if bank else VerificationStatus.NOT_FOUND,
            latency_ms=round((perf_counter() - start) * 1000),
            reference_id=sha256(routing_code.encode()).hexdigest()[:16],
            resolved_bank_name=bank["name"] if bank else None,
            details={"simulation": "fictional_bank_prefix_reference"},
        )

    def verify_account(self, account_number: str, routing_code: str, account_holder_name: str,
                       bank_name: str | None, country: str, currency: str | None):
        start = perf_counter()
        code = "".join(routing_code.split()).upper()
        bank = self._bank(routing_code)
        routing_valid = bool(bank) or (len(code) > 4 and iban_is_valid(code))
        status = VerificationStatus.VERIFIED if routing_valid else VerificationStatus.NOT_FOUND
        return BankVerificationResult(
            capability="bank_account", provider_name=self.provider_name,
            mode=VerificationMode.LOCAL_SIMULATED, status=status,
            latency_ms=round((perf_counter() - start) * 1000),
            reference_id=sha256((account_number + routing_code).encode()).hexdigest()[:16],
            account_active=True if routing_valid and account_number else None,
            resolved_bank_name=bank["name"] if bank else None,
            holder_name_match_score=None,
            details={"simulation": "local_syntax_and_fictional_bank_reference_only"},
        )
