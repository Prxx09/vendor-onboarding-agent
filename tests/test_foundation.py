from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.agents.smoke import SmokeAgent
from app.config import Settings, get_settings
from app.llm.errors import LLMOutputError, LLMProviderError, MockResponseNotConfigured
from app.llm.factory import get_llm_provider
from app.llm.groq_provider import GroqProvider
from app.llm.mock_provider import MockProvider
from app.prompts.loader import load_prompt
from app.schemas.common import AgentStatus


class Reply(BaseModel):
    value: str


class FakeCompletions:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value))])


class FakeClient:
    def __init__(self, values):
        completions = FakeCompletions(values)
        self.chat = SimpleNamespace(completions=completions)
        self.completions = completions


def test_settings_defaults_without_secrets(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("REPOSITORY_BACKEND", raising=False)
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "mock"
    assert settings.groq_api_key is None
    assert settings.repository_backend == "memory"
    get_settings.cache_clear()


def test_factory_selects_mock(settings):
    assert isinstance(get_llm_provider(settings), MockProvider)


def test_mock_provider_registered_response_and_records_call():
    provider = MockProvider({"Reply": {"value": "ok"}})
    assert provider.generate_structured(system="s", user="u", schema=Reply).value == "ok"
    assert provider.calls == [{"system": "s", "user": "u", "schema": "Reply", "key": None}]


def test_mock_provider_missing_response():
    with pytest.raises(MockResponseNotConfigured):
        MockProvider().generate_structured(system="", user="", schema=Reply)


def test_mock_provider_failure_injection():
    with pytest.raises(RuntimeError, match="injected"):
        MockProvider(fail_with=RuntimeError("injected")).generate_structured(
            system="", user="", schema=Reply
        )


def test_groq_valid_json(settings):
    client = FakeClient(['{"value":"ok"}'])
    assert GroqProvider(settings, client).generate_structured(system="s", user="u", schema=Reply).value == "ok"
    assert client.completions.calls[0]["temperature"] == 0
    assert client.completions.calls[0]["response_format"] == {"type": "json_object"}


def test_groq_invalid_then_valid(settings):
    client = FakeClient(['{"wrong":true}', '{"value":"fixed"}'])
    assert GroqProvider(settings, client).generate_structured(system="s", user="u", schema=Reply).value == "fixed"
    assert len(client.completions.calls) == 2
    assert "failed validation" in client.completions.calls[1]["messages"][0]["content"]


def test_groq_invalid_twice(settings):
    client = FakeClient(['{"wrong":true}', '{"wrong":false}'])
    with pytest.raises(LLMOutputError):
        GroqProvider(settings, client).generate_structured(system="s", user="u", schema=Reply)


def test_groq_api_error(settings):
    settings.groq_max_retries = 0
    client = FakeClient([RuntimeError("offline")])
    with pytest.raises(LLMProviderError):
        GroqProvider(settings, client).generate_structured(system="s", user="u", schema=Reply)


def test_prompt_loader_renders_and_rejects_missing():
    assert "sample" in load_prompt("smoke", text="sample")
    with pytest.raises(ValueError, match="text"):
        load_prompt("smoke")


def test_smoke_agent_happy_path():
    provider = MockProvider({"smoke": {"summary": "A summary", "word_count": 2}})
    result = SmokeAgent(provider).run({"text": "hello world"})
    assert result.status == AgentStatus.OK
    assert result.data.word_count == 2
    assert len(provider.calls) == 1


def test_smoke_agent_failure_path():
    provider = MockProvider()
    result = SmokeAgent(provider).run({"text": "hello"})
    assert result.status == AgentStatus.NEEDS_MANUAL_REVIEW
    assert result.data is None
    assert result.error
