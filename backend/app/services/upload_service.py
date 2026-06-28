from __future__ import annotations

from io import BytesIO
import logging
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CourseGroup, Syllabus
from app.services.analysis_queue import enqueue_report_analysis
from app.services.filename_parser import FilenameParseError, parse_syllabus_filename, slugify_filename
from app.services.pdf_extractor import extract_pdf_text
from app.services.report_service import create_queued_analysis_report
from app.services.storage_service import (
    StorageError,
    delete_pdf,
    materialize_pdf_bytes,
    upload_pdf,
)


logger = logging.getLogger(__name__)


def _get_or_create_course_group(db: Session, parsed, user_id: str) -> CourseGroup:
    group = (
        db.query(CourseGroup)
        .filter(
            CourseGroup.user_id == user_id,
            CourseGroup.academic_period == parsed.academic_period,
            CourseGroup.course_code == parsed.course_code,
        )
        .one_or_none()
    )
    if group:
        if group.course_name != parsed.course_name:
            group.course_name = parsed.course_name
        return group

    group = CourseGroup(
        user_id=user_id,
        academic_period=parsed.academic_period,
        year=parsed.year,
        term=parsed.term,
        course_code=parsed.course_code,
        career=parsed.career,
        course_name=parsed.course_name,
    )
    db.add(group)
    db.flush()
    return group


def process_zip_upload(db: Session, filename: str, content: bytes, user_id: str) -> dict:
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        return {
            "accepted_count": 0,
            "rejected_count": 1,
            "rejected_files": [{"filename": filename, "reason": f"El ZIP supera {settings.max_upload_mb} MB"}],
            "course_ids": [],
            "message": "Carga rechazada por tamaño",
        }

    accepted = 0
    rejected: list[dict[str, str]] = []
    course_ids: set[int] = set()
    queued_report_ids: list[int] = []
    uploaded_paths: list[str] = []

    try:
        archive = ZipFile(BytesIO(content))
    except BadZipFile:
        return {
            "accepted_count": 0,
            "rejected_count": 1,
            "rejected_files": [{"filename": filename, "reason": "El archivo no es un ZIP válido"}],
            "course_ids": [],
            "message": "Carga rechazada",
        }

    try:
        with archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue

                original_name = Path(member.filename).name
                if not original_name:
                    continue

                try:
                    parsed = parse_syllabus_filename(original_name)
                except FilenameParseError as exc:
                    rejected.append({"filename": original_name, "reason": str(exc)})
                    continue

                raw_pdf = archive.read(member)
                safe_name = slugify_filename(original_name)
                object_key = (
                    f"{parsed.academic_period}/{parsed.course_code}/"
                    f"{uuid4().hex}_{safe_name}"
                )

                extraction_status = "ok"
                extraction_error = None
                try:
                    with materialize_pdf_bytes(raw_pdf, original_name) as temp_path:
                        text_content = extract_pdf_text(temp_path)
                    if not text_content:
                        extraction_status = "empty"
                        extraction_error = "No se pudo extraer texto; puede ser un PDF escaneado."
                except Exception as exc:
                    text_content = ""
                    extraction_status = "error"
                    extraction_error = str(exc)

                try:
                    stored_path = upload_pdf(object_key, raw_pdf)
                except StorageError as exc:
                    rejected.append({"filename": original_name, "reason": str(exc)})
                    continue
                uploaded_paths.append(stored_path)

                group = _get_or_create_course_group(db, parsed, user_id)
                syllabus = Syllabus(
                    course_group_id=group.id,
                    original_filename=original_name,
                    stored_path=stored_path,
                    file_size=len(raw_pdf),
                    academic_period=parsed.academic_period,
                    year=parsed.year,
                    term=parsed.term,
                    career=parsed.career,
                    course_code=parsed.course_code,
                    nrc=parsed.nrc,
                    course_name=parsed.course_name,
                    text_content=text_content,
                    extraction_status=extraction_status,
                    extraction_error=extraction_error,
                )
                db.add(syllabus)
                db.flush()
                course_ids.add(group.id)
                accepted += 1

        for course_id in sorted(course_ids):
            report = create_queued_analysis_report(db, course_id)
            queued_report_ids.append(report.id)

        db.commit()
    except Exception:
        db.rollback()
        for stored_path in uploaded_paths:
            try:
                delete_pdf(stored_path)
            except StorageError:
                logger.exception("Could not clean up uploaded object %s", stored_path)
        raise

    for report_id in queued_report_ids:
        enqueue_report_analysis(report_id)

    return {
        "accepted_count": accepted,
        "rejected_count": len(rejected),
        "rejected_files": rejected,
        "course_ids": sorted(course_ids),
        "queued_report_ids": queued_report_ids,
        "message": f"Se cargaron {accepted} syllabus PDF y se encolaron {len(queued_report_ids)} análisis",
    }
