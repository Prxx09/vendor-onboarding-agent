from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-3.8-flash"

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
