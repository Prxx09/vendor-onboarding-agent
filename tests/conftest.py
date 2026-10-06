import pytest

from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)
