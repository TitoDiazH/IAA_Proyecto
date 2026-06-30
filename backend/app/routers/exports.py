from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.schemas import ConditionsExportTable
from app.services.conditions_export import (
    build_conditions_export_table,
    conditions_table_to_csv,
    conditions_table_to_xlsx,
)


router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.get("/conditions", response_model=ConditionsExportTable)
def get_conditions_export_table(
    academic_period: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    return build_conditions_export_table(db, current_user["id"], academic_period)


@router.get("/conditions/download")
def download_conditions_export(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    filename: str = Query("condiciones-aprobacion"),
    academic_period: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Response:
    table = build_conditions_export_table(db, current_user["id"], academic_period)
    safe_filename = _safe_filename(filename) or "condiciones-aprobacion"

    if format == "csv":
        content = conditions_table_to_csv(table).encode("utf-8-sig")
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}.csv"'},
        )

    if format == "xlsx":
        content = conditions_table_to_xlsx(table)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}.xlsx"'},
        )

    raise HTTPException(status_code=400, detail="Formato de exportación no soportado")


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-")
