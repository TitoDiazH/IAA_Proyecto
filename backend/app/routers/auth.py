from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import _supabase_admin, get_current_user, require_admin
from app.database import get_db
from app.schemas import ModelPreference, ModelPreferenceUpdate
from app.services.user_preferences import (
    get_preferred_model,
    is_valid_model,
    list_available_models,
    set_preferred_model,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_VALID_ROLES = frozenset({"admin", "user"})


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)) -> dict:
    return current_user


@router.get("/models", response_model=ModelPreference)
async def get_model_preference(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    return {
        "available": list_available_models(),
        "selected": get_preferred_model(db, current_user["id"]),
    }


@router.put("/models", response_model=ModelPreference)
async def update_model_preference(
    payload: ModelPreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    if not is_valid_model(payload.model):
        raise HTTPException(status_code=400, detail="Modelo no disponible.")

    set_preferred_model(db, current_user["id"], payload.model)
    return {
        "available": list_available_models(),
        "selected": payload.model,
    }


@router.patch("/users/{user_id}/role")
async def set_user_role(
    user_id: str,
    role: str,
    _admin: dict = Depends(require_admin),
) -> dict:
    if role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="Rol inválido. Use 'admin' o 'user'.")

    supabase = _supabase_admin()
    try:
        supabase.table("profiles").update({"role": role}).eq("id", user_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="No se pudo actualizar el rol") from exc

    return {"user_id": user_id, "role": role}
