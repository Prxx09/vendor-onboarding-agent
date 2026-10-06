import pytest

from app.config import Settings
from app.repositories.factory import get_repository
from app.repositories.memory import InMemoryRepository
from app.schemas.domain import RequestType, VendorRequest


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture(params=["memory", pytest.param("supabase", marks=pytest.mark.integration)])
def repository(request, monkeypatch):
    if request.param == "memory":
        return InMemoryRepository()
    monkeypatch.setenv("REPOSITORY_BACKEND", "supabase")
    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        pytest.skip("SUPABASE_URL and SUPABASE_SERVICE_KEY are not configured")
    return get_repository(settings)


@pytest.fixture
def contract_request(repository):
    model = VendorRequest(request_type=RequestType.NEW_SUPPLIER, supplier_name="Test Fixture Vendor")
    created = repository.create_request(model)
    yield created
    if hasattr(repository, "client"):
        repository.client.table("vendor_requests").delete().eq("id", created.id).execute()
