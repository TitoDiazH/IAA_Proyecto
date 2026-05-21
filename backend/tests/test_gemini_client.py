from types import SimpleNamespace

import pytest

from app.services.ai_client import AIConfigurationError, AIProviderError, GeminiJsonClient
from app.services.ai_client import get_json_client


class DummyResponse:
    def __init__(self, *, text=None, parsed=None):
        self.text = text
        self.parsed = parsed


class DummyModels:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.error is not None:
            raise self.error
        return self.response


class DummyClient:
    def __init__(self, models):
        self.models = models
        self.init_kwargs = None


def test_gemini_client_uses_json_schema_config(monkeypatch):
    dummy = DummyClient(DummyModels(DummyResponse(text='{"ok": true}')))

    def client_factory(**kwargs):
        dummy.init_kwargs = kwargs
        return dummy

    monkeypatch.setattr("app.services.ai_client.genai", SimpleNamespace(Client=client_factory))
    monkeypatch.setattr("app.services.ai_client.genai_types", None)

    client = GeminiJsonClient(
        api_key="test-key",
        model="gemini-2.5-flash",
        timeout_seconds=30,
    )

    result = client.complete_json(
        system_prompt="system",
        user_prompt="user",
        schema_name="example",
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
    )

    assert result == {"ok": True}
    assert dummy.init_kwargs == {"api_key": "test-key"}
    assert dummy.models.calls == [
        {
            "model": "gemini-2.5-flash",
            "contents": "user",
            "config": {
                "system_instruction": "system",
                "temperature": 0,
                "response_mime_type": "application/json",
                "response_json_schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
            },
        }
    ]


def test_gemini_client_accepts_parsed_dict(monkeypatch):
    dummy = DummyClient(DummyModels(DummyResponse(parsed={"ok": True})))
    monkeypatch.setattr("app.services.ai_client.genai", SimpleNamespace(Client=lambda **kwargs: dummy))
    monkeypatch.setattr("app.services.ai_client.genai_types", None)

    client = GeminiJsonClient(api_key="test-key", model="gemini-2.5-flash", timeout_seconds=30)

    result = client.complete_json(
        system_prompt="system",
        user_prompt="user",
        schema_name="example",
        schema={"type": "object", "properties": {}},
    )

    assert result == {"ok": True}


def test_gemini_client_reports_provider_errors(monkeypatch):
    dummy = DummyClient(DummyModels(error=RuntimeError("quota exceeded")))
    monkeypatch.setattr("app.services.ai_client.genai", SimpleNamespace(Client=lambda **kwargs: dummy))
    monkeypatch.setattr("app.services.ai_client.genai_types", None)

    client = GeminiJsonClient(api_key="test-key", model="gemini-2.5-flash", timeout_seconds=30)

    with pytest.raises(AIProviderError, match="Gemini falló.*quota exceeded"):
        client.complete_json(
            system_prompt="system",
            user_prompt="user",
            schema_name="example",
            schema={"type": "object", "properties": {}},
        )


def test_gemini_client_requires_api_key(monkeypatch):
    monkeypatch.setattr("app.services.ai_client.genai", SimpleNamespace(Client=lambda **kwargs: object()))

    with pytest.raises(AIConfigurationError, match="GEMINI_API_KEY"):
        GeminiJsonClient(api_key="", model="gemini-2.5-flash", timeout_seconds=30)


def test_get_json_client_returns_gemini_client(monkeypatch):
    class FakeSettings:
        ai_request_timeout_seconds = 15
        gemini_api_key = "test-key"
        gemini_model = "gemini-2.5-flash"

    monkeypatch.setattr("app.services.ai_client.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("app.services.ai_client.genai", SimpleNamespace(Client=lambda **kwargs: object()))
    monkeypatch.setattr("app.services.ai_client.genai_types", None)

    client = get_json_client()

    assert isinstance(client, GeminiJsonClient)
