from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: Literal["mock", "groq"] = "mock"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_timeout_seconds: int = 30
    groq_max_retries: int = 2
    repository_backend: Literal["memory", "supabase"] = "memory"
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    log_level: str = "INFO"
    low_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
