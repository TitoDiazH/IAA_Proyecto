from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import UploadResponse
from app.services.upload_service import process_zip_upload


router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("/zip", response_model=UploadResponse)
async def upload_zip(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Debes subir un archivo ZIP")

    content = await file.read()
    return process_zip_upload(db, file.filename, content)

