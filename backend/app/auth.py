import logging
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import Client, create_client

from app.config import get_settings

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=True)


@lru_cache(maxsize=1)
def _supabase_admin() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_backend_key)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    token = credentials.credentials
    supabase = _supabase_admin()

    try:
        auth_response = supabase.auth.get_user(token)
    except Exception as exc:
        logger.debug("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o sesión expirada",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not auth_response or not auth_response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o sesión expirada",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = str(auth_response.user.id)
    user_email = auth_response.user.email or ""

    return {"id": user_id, "email": user_email}
