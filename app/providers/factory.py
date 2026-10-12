from app.core.config import get_settings
from app.providers.base import VerificationProvider
from app.providers.http_provider import HttpVerificationProvider
from app.providers.supabase_provider import SupabaseVerificationProvider


def get_verification_provider() -> VerificationProvider:
    mode = get_settings().VERIFICATION_PROVIDER_MODE.lower()

    if mode == "supabase":
        return SupabaseVerificationProvider()
    if mode == "http":
        return HttpVerificationProvider()

    raise ValueError(f"Unsupported VERIFICATION_PROVIDER_MODE={mode}")
