from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from app.config import get_settings


class AIConfigurationError(RuntimeError):
    """Raised when the AI provider is not configured correctly."""


class AIProviderError(RuntimeError):
    """Raised when the AI provider fails or returns an invalid response."""


class JsonCompletionClient(Protocol):
    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]: ...


class OllamaJsonClient:
    """HTTP client for local Ollama chat completions with JSON-schema output."""

    def __init__(self, base_url: str, model: str, timeout_seconds: int) -> None:
        if not base_url:
            raise AIConfigurationError("Falta configurar OLLAMA_BASE_URL para usar Ollama.")
        if not model:
            raise AIConfigurationError("Falta configurar LOCAL_LLM_MODEL para usar Ollama.")

        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def _chat_url(self) -> str:
        return f"{self.base_url}/api/chat"

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            data = response.json()
        except json.JSONDecodeError:
            return response.text.strip()

        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, str):
                return error
        return response.text.strip()

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        url = self._chat_url()
        base_payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0},
        }

        payloads = [
            {**base_payload, "format": schema},
            {**base_payload, "format": "json"},
        ]

        response: httpx.Response | None = None
        for payload_index, payload in enumerate(payloads):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, json=payload)
            except httpx.TimeoutException as exc:
                raise AIProviderError(f"Ollama agotó el tiempo de espera en {url}: {exc}") from exc
            except httpx.RequestError as exc:
                raise AIProviderError(f"No se pudo conectar a Ollama en {url}: {exc}") from exc

            if response.status_code == 404:
                detail = self._error_detail(response)
                detail_text = f" Detalle: {detail}." if detail else ""
                raise AIProviderError(
                    f"Ollama respondió 404 en {url}.{detail_text} Verifica que Ollama esté corriendo "
                    f"y que el modelo {self.model} exista."
                )

            if response.status_code < 400:
                break

            should_try_fallback = payload_index == 0 and response.status_code in {400, 422}
            if should_try_fallback:
                error_text = response.text.lower()
                if any(token in error_text for token in ["format", "schema", "json"]):
                    continue

            raise AIProviderError(f"Ollama respondió con error {response.status_code} en {url}: {response.text}")

        if response is None:
            raise AIProviderError(f"No se recibió respuesta válida de Ollama en {url}.")

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise AIProviderError("Ollama devolvió una respuesta no JSON.") from exc

        message = data.get("message") or {}
        text = message.get("content") if isinstance(message, dict) else None
        if not text:
            raise AIProviderError("Ollama no devolvió contenido para el análisis.")

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIProviderError("Ollama no devolvió JSON válido.") from exc


def get_json_client() -> JsonCompletionClient:
    settings = get_settings()
    return OllamaJsonClient(
        base_url=settings.ollama_base_url,
        model=settings.local_model,
        timeout_seconds=settings.ai_request_timeout_seconds,
    )
