from __future__ import annotations

import logging
import threading
import time

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import UserPreference

try:
    from google import genai
except ImportError:  # pragma: no cover - allows importing this module in minimal test envs
    genai = None

logger = logging.getLogger(__name__)

# Models listed by the API that aren't suited to this app's one-shot JSON
# completion use case (embeddings, image/video/audio/tts generation, live
# streaming, open-weight Gemma, etc.).
_EXCLUDED_NAME_TOKENS = (
    "embedding",
    "aqa",
    "image",  # covers imagen, "-image", "-image-preview" (e.g. Nano Banana) variants
    "veo",
    "vision",
    "gemma",
    "tts",
    "live",
    "native-audio",
    "computer-use",
    "robotics",
)

# Used only if we've never successfully reached Google's API (e.g. first
# request after a fresh deploy with a network hiccup).
_FALLBACK_MODELS: list[dict[str, str]] = [
    {
        "id": "gemini-2.5-flash",
        "label": "Gemini 2.5 Flash",
        "description": "Rápido y económico. Recomendado para uso general.",
    },
    {
        "id": "gemini-2.5-pro",
        "label": "Gemini 2.5 Pro",
        "description": "Más capaz para casos ambiguos, pero más lento y con menor cuota disponible.",
    },
]

_CACHE_TTL_SECONDS = 3600
_model_cache: dict[str, object] = {"models": None, "fetched_at": 0.0}


def default_model() -> str:
    return get_settings().gemini_model


def _fetch_models_from_google() -> list[dict[str, str]]:
    settings = get_settings()
    if genai is None or not settings.gemini_api_key:
        return []

    client = genai.Client(api_key=settings.gemini_api_key)
    models: list[dict[str, str]] = []
    for item in client.models.list():
        name = str(item.name or "").removeprefix("models/")
        if not name.startswith("gemini"):
            continue
        if any(token in name for token in _EXCLUDED_NAME_TOKENS):
            continue
        supported_actions = getattr(item, "supported_actions", None) or []
        if "generateContent" not in supported_actions:
            continue
        models.append(
            {
                "id": name,
                "label": getattr(item, "display_name", None) or name,
                "description": getattr(item, "description", None) or "",
            }
        )
    return models


def list_available_models() -> list[dict[str, str]]:
    """List Gemini models available to this app's API key, straight from Google.

    Cached for a while so new model releases show up on their own (no code
    change needed) without hitting Google's API on every page load.
    """

    now = time.monotonic()
    cached_models = _model_cache["models"]
    if cached_models is not None and now - _model_cache["fetched_at"] < _CACHE_TTL_SECONDS:
        return cached_models

    try:
        fetched = _fetch_models_from_google()
    except Exception as exc:
        logger.warning("Could not list Gemini models from Google: %s", exc)
        fetched = []

    models = fetched or cached_models or _FALLBACK_MODELS
    _model_cache["models"] = models
    _model_cache["fetched_at"] = now
    return models


def warm_model_cache() -> None:
    """Fetch the model list once in the background so the first real request
    (e.g. the Homepage's model selector) doesn't have to wait on Google's API."""

    threading.Thread(target=list_available_models, daemon=True).start()


def is_valid_model(model: str) -> bool:
    return any(item["id"] == model for item in list_available_models())


def get_preferred_model(db: Session, user_id: str | None) -> str:
    if not user_id:
        return default_model()

    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).one_or_none()
    if pref and pref.gemini_model and is_valid_model(pref.gemini_model):
        return pref.gemini_model
    return default_model()


def set_preferred_model(db: Session, user_id: str, model: str) -> UserPreference:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).one_or_none()
    if pref is None:
        pref = UserPreference(user_id=user_id, gemini_model=model)
        db.add(pref)
    else:
        pref.gemini_model = model
    db.commit()
    db.refresh(pref)
    return pref
