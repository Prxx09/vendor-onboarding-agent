from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # Groq structures the text extracted locally by Windows OCR / PyMuPDF.
    GROQ_API_KEY: str
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    GROQ_MAX_RETRIES: int = 3

    # Local document extraction.
    OCR_PROVIDER: str = "windows"
    OCR_LANGUAGE: str | None = None
    OCR_MAX_PDF_PAGES: int = 20
    OCR_PDF_RENDER_SCALE: float = 2.0
    PDF_NATIVE_TEXT_MIN_CHARS: int = 40
    DOCUMENT_TEXT_MAX_CHARS: int = 30000

    # Frontend/backend policy is supplied by the backend; the frontend does
    # not embed upload limits, thresholds, users, regions or categories.
    MAX_UPLOAD_FILES: int = 8
    MAX_FILE_SIZE_MB: int = 20
    MAX_COMBINED_UPLOAD_MB: int = 100
    AUTO_APPROVAL_THRESHOLD: float | None = None
    REQUIRED_INTAKE_FIELDS: str = (
        "legal_name,tax_id,bank_account,ifsc,registered_address,compliance_confirmed"
    )
    VENDOR_REGIONS: str = ""
    VENDOR_CATEGORIES: str = ""
    TAX_ID_PATTERN: str = ""
    PAN_PATTERN: str = ""
    IFSC_PATTERN: str = ""
    DOCUMENT_STORAGE_BUCKET: str = "verification-documents"

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
