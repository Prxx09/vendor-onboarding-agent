from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-3.8-flash"

    # Local document extraction.
    OCR_PROVIDER: str = "windows"
    OCR_LANGUAGE: str | None = None
    OCR_MAX_PDF_PAGES: int = 20
    OCR_PDF_RENDER_SCALE: float = 2.0
    PDF_NATIVE_TEXT_MIN_CHARS: int = 40
    DOCUMENT_TEXT_MAX_CHARS: int = 30000

    VERIFICATION_PROVIDER_MODE: str = "supabase"

    COMPANY_REGISTRY_API_URL: str | None = None
    TAX_REGISTRY_API_URL: str | None = None
    BANK_VERIFICATION_API_URL: str | None = None
    KYC_API_URL: str | None = None
    SANCTIONS_API_URL: str | None = None
    OFFICIAL_API_KEY: str | None = None
    OFFICIAL_API_KEY_HEADER: str = "Authorization"


@lru_cache
def get_settings() -> Settings:
    return Settings()
