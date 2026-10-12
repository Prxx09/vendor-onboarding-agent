from rapidfuzz.fuzz import token_set_ratio
from supabase import Client, create_client

from app.core.config import get_settings
from app.domain.models import VerificationEvidence
from app.providers.base import VerificationProvider


def _name_score(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return token_set_ratio(a.lower(), b.lower()) / 100.0


class SupabaseVerificationProvider(VerificationProvider):
    """Synthetic verification backend used by the client-demo MVP."""

    def __init__(self) -> None:
        settings = get_settings()
        self.db: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )

    async def verify_company(self, registration_number: str) -> VerificationEvidence:
        result = (
            self.db.table("company_registry")
            .select("*")
            .eq("registration_number", registration_number)
            .limit(1)
            .execute()
        )
        if not result.data:
            return VerificationEvidence(
                source="company_registry",
                status="NOT_FOUND",
                message="Business registration was not found in the verification registry.",
            )

        row = result.data[0]
        active = row.get("registration_status") == "ACTIVE"
        return VerificationEvidence(
            source="company_registry",
            status="VERIFIED" if active else "REVIEW_REQUIRED",
            message=(
                "Business registration is active."
                if active
                else f"Business registration status is {row.get('registration_status', 'UNKNOWN')}."
            ),
            data=row,
        )

    async def verify_tax(self, tax_id: str) -> VerificationEvidence:
        result = (
            self.db.table("tax_registry")
            .select("*")
            .eq("tax_id", tax_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return VerificationEvidence(
                source="tax_registry",
                status="NOT_FOUND",
                message="Tax ID was not found in the verification registry.",
            )

        row = result.data[0]
        active = row.get("tax_status") == "ACTIVE"
        return VerificationEvidence(
            source="tax_registry",
            status="VERIFIED" if active else "REVIEW_REQUIRED",
            message="Tax registration is active." if active else "Tax registration is not active.",
            data=row,
        )

    async def verify_bank(
        self,
        account_number: str,
        ifsc_swift: str | None,
        expected_account_holder: str | None,
    ) -> VerificationEvidence:
        query = (
            self.db.table("bank_account_registry")
            .select("*")
            .eq("account_number", account_number)
        )
        if ifsc_swift:
            query = query.eq("ifsc_swift", ifsc_swift)

        result = query.limit(1).execute()
        if not result.data:
            return VerificationEvidence(
                source="bank_account_registry",
                status="NOT_FOUND",
                message="Bank account was not found in the verification registry.",
            )

        row = result.data[0]
        actual_name = row.get("account_holder_legal_name")
        score = _name_score(expected_account_holder, actual_name) if expected_account_holder else 1.0

        if row.get("account_status") != "ACTIVE":
            status = "REVIEW_REQUIRED"
            message = "Bank account exists but is not active."
        elif expected_account_holder and score < 0.80:
            status = "MISMATCH"
            message = f"Bank account-holder name mismatch (similarity {score:.0%})."
        else:
            status = "VERIFIED"
            message = f"Bank account verified (name similarity {score:.0%})."

        return VerificationEvidence(
            source="bank_account_registry",
            status=status,
            message=message,
            data={**row, "name_match_score": score},
        )

    async def verify_kyc(
        self,
        legal_name: str,
        registration_number: str | None,
        tax_id: str | None,
    ) -> VerificationEvidence:
        query = self.db.table("kyc_registry").select("*")

        if registration_number:
            query = query.eq("registration_number", registration_number)
        elif tax_id:
            query = query.eq("tax_id", tax_id)
        else:
            query = query.ilike("legal_name", legal_name)

        result = query.limit(1).execute()
        if not result.data:
            return VerificationEvidence(
                source="kyc_registry",
                status="NOT_FOUND",
                message="KYC/KYB profile was not found in the verification registry.",
            )

        row = result.data[0]
        risky = (
            row.get("kyc_status") != "VERIFIED"
            or row.get("beneficial_owner_check") not in (None, "CLEAR")
            or row.get("document_check_status") not in (None, "COMPLETE")
            or bool(row.get("risk_country_flag"))
        )

        return VerificationEvidence(
            source="kyc_registry",
            status="REVIEW_REQUIRED" if risky else "VERIFIED",
            message="KYC/KYB profile requires review." if risky else "KYC/KYB profile verified.",
            data=row,
        )

    async def check_sanctions(self, legal_name: str) -> VerificationEvidence:
        result = (
            self.db.table("sanctions_registry")
            .select("*")
            .ilike("entity_name", legal_name)
            .eq("active", True)
            .limit(1)
            .execute()
        )

        if not result.data:
            return VerificationEvidence(
                source="sanctions_registry",
                status="VERIFIED",
                message="No sanctions/watchlist match found.",
                data={"match": False},
            )

        return VerificationEvidence(
            source="sanctions_registry",
            status="REVIEW_REQUIRED",
            message="Potential sanctions/watchlist match found.",
            data={"match": True, **result.data[0]},
        )

    async def check_duplicate_tax_id(self, tax_id: str) -> VerificationEvidence:
        try:
            live = (
                self.db.table("vendor_master")
                .select("*")
                .eq("tax_id", tax_id)
                .limit(1)
                .execute()
            )
        except Exception:
            live = None

        if live and live.data:
            return VerificationEvidence(
                source="vendor_master",
                status="REVIEW_REQUIRED",
                message="Tax ID already belongs to a vendor in the global Vendor Master.",
                data=live.data[0],
            )

        result = (
            self.db.table("vendor_master_snapshot")
            .select("*")
            .eq("tax_id", tax_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return VerificationEvidence(
                source="vendor_master_snapshot",
                status="REVIEW_REQUIRED",
                message="Tax ID already exists in the reference vendor master.",
                data=result.data[0],
            )

        return VerificationEvidence(
            source="vendor_master",
            status="VERIFIED",
            message="No duplicate Tax ID found in the global Vendor Master.",
            data={"duplicate": False},
        )
