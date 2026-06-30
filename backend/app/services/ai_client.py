from __future__ import annotations

import json
from typing import Any, Protocol

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - exercised only in environments missing optional deps
    genai = None
    genai_types = None

from app.config import get_settings


class AIConfigurationError(RuntimeError):
    """Raised when the AI provider is not configured correctly."""


class AIProviderError(RuntimeError):
    """Raised when the AI provider fails or returns an invalid response."""


class AIQuotaExceededError(AIProviderError):
    """Raised when the AI provider reports its request quota/rate limit was exceeded."""


class JsonCompletionClient(Protocol):
    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]: ...


class GeminiJsonClient:
    """Client for Gemini JSON completions through the Google Gen AI SDK."""

    def __init__(self, api_key: str, model: str, timeout_seconds: int) -> None:
        if not api_key:
            raise AIConfigurationError("Falta configurar GEMINI_API_KEY para usar Gemini.")
        if not model:
            raise AIConfigurationError("Falta configurar GEMINI_MODEL para usar Gemini.")
        if genai is None:
            raise AIConfigurationError("Falta instalar la dependencia google-genai para usar Gemini.")

        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = self._build_client()

    def _build_client(self) -> Any:
        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if genai_types is not None:
            kwargs["http_options"] = genai_types.HttpOptions(
                client_args={"timeout": self.timeout_seconds},
            )
        return genai.Client(**kwargs)

    @staticmethod
    def _provider_error_message(exc: Exception) -> str:
        code = getattr(exc, "code", None)
        message = getattr(exc, "message", None) or str(exc)
        return f"{code}: {message}" if code else message

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        code = getattr(exc, "code", None)
        text = f"{code} {getattr(exc, 'message', None) or exc}".upper()
        return code == 429 or "RESOURCE_EXHAUSTED" in text or "QUOTA" in text or "RATE LIMIT" in text

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        config: dict[str, Any] = {
            "system_instruction": system_prompt,
            "temperature": 0,
            "response_mime_type": "application/json",
            "response_json_schema": schema,
        }

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=config,
            )
        except Exception as exc:
            detail = self._provider_error_message(exc)
            message = f"Gemini falló al generar {schema_name}: {detail}"
            if self._is_quota_error(exc):
                raise AIQuotaExceededError(message) from exc
            raise AIProviderError(message) from exc

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, dict):
            return parsed

        text = getattr(response, "text", None)
        if not text:
            raise AIProviderError("Gemini no devolvió contenido para el análisis.")

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIProviderError("Gemini no devolvió JSON válido.") from exc


def get_json_client() -> JsonCompletionClient:
    settings = get_settings()
    return GeminiJsonClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout_seconds=settings.ai_request_timeout_seconds,
    )
