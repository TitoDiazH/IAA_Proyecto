from io import BytesIO
from zipfile import is_zipfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.schemas import UploadResponse
from app.services.upload_service import process_zip_upload


router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("/zip", response_model=UploadResponse)
async def upload_zip(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    content = await file.read()
    if not content or not is_zipfile(BytesIO(content)):
        received_name = file.filename or "archivo sin nombre"
        raise HTTPException(
            status_code=400,
            detail=f"{received_name}: el contenido no corresponde a un archivo ZIP válido",
        )

    return process_zip_upload(db, file.filename or "upload.zip", content, current_user["id"])
