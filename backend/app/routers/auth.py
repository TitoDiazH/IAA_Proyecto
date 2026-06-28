from fastapi import APIRouter, Depends, HTTPException

from app.auth import _supabase_admin, get_current_user, require_admin

router = APIRouter(prefix="/api/auth", tags=["auth"])

_VALID_ROLES = frozenset({"admin", "user"})


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)) -> dict:
    return current_user


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
