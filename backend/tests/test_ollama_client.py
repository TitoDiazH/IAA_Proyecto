from app.services.ai_client import OllamaJsonClient
from app.services.ai_client import get_json_client


class DummyResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload
        self.headers = {}

    @property
    def text(self):
        return str(self._payload)

    def json(self):
        return self._payload


class DummyClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json=None):
        self.calls.append({"url": url, "json": json})
        return self.response


def test_ollama_client_uses_api_chat_and_schema_format(monkeypatch):
    dummy_client = DummyClient(DummyResponse({"message": {"content": '{"ok": true}'}}))
    monkeypatch.setattr("app.services.ai_client.httpx.Client", lambda timeout: dummy_client)

    client = OllamaJsonClient(
        base_url="http://localhost:11434",
        model="qwen2.5:14b",
        timeout_seconds=30,
    )

    result = client.complete_json(
        system_prompt="system",
        user_prompt="user",
        schema_name="example",
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
    )

    assert result == {"ok": True}
    assert dummy_client.calls[0]["url"] == "http://localhost:11434/api/chat"
    assert dummy_client.calls[0]["json"]["stream"] is False
    assert dummy_client.calls[0]["json"]["options"]["temperature"] == 0
    assert dummy_client.calls[0]["json"]["format"]["type"] == "object"


def test_ollama_client_reports_missing_model(monkeypatch):
    class NotFoundResponse(DummyResponse):
        status_code = 404

    dummy_client = DummyClient(NotFoundResponse({"error": "model not found"}))
    monkeypatch.setattr("app.services.ai_client.httpx.Client", lambda timeout: dummy_client)

    client = OllamaJsonClient(
        base_url="http://localhost:11434",
        model="qwen2.5:14b",
        timeout_seconds=30,
    )

    try:
        client.complete_json(
            system_prompt="system",
            user_prompt="user",
            schema_name="example",
            schema={"type": "object", "properties": {}},
        )
    except Exception as exc:
        assert "404" in str(exc)
        assert "qwen2.5:14b" in str(exc)
        assert "model not found" in str(exc)


def test_get_json_client_returns_ollama_client(monkeypatch):
    class FakeSettings:
        ai_request_timeout_seconds = 15
        ollama_base_url = "http://localhost:11434"
        local_model = "qwen2.5:14b"

    monkeypatch.setattr("app.services.ai_client.get_settings", lambda: FakeSettings())

    client = get_json_client()

    assert isinstance(client, OllamaJsonClient)

