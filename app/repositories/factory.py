from app.config import Settings, get_settings
from app.repositories.base import OnboardingRepository
from app.repositories.memory import InMemoryRepository
from app.repositories.supabase_repo import SupabaseRepository


def get_repository(settings: Settings | None = None) -> OnboardingRepository:
    settings = settings or get_settings()
    if settings.repository_backend == "supabase":
        return SupabaseRepository(settings)
    return InMemoryRepository()
