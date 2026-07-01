from io import BytesIO
from zipfile import is_zipfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.schemas import UploadResponse
from app.services.upload_service import process_pdf_uploads, process_zip_upload


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


@router.post("/pdfs", response_model=UploadResponse)
async def upload_pdfs(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    entries: list[tuple[str, bytes]] = []
    rejected: list[dict[str, str]] = []
    for file in files:
        content = await file.read()
        filename = file.filename or "archivo.pdf"
        if not content or not content.startswith(b"%PDF-"):
            rejected.append({"filename": filename, "reason": "El contenido no corresponde a un archivo PDF válido"})
            continue
        entries.append((filename, content))

    result = process_pdf_uploads(db, entries, current_user["id"])
    result["rejected_files"] = rejected + result["rejected_files"]
    result["rejected_count"] = len(result["rejected_files"])
    return result
