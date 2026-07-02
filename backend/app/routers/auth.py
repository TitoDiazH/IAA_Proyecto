from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.schemas import ModelPreference, ModelPreferenceUpdate
from app.services.user_preferences import (
    get_preferred_model,
    is_valid_model,
    list_available_models,
    set_preferred_model,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
