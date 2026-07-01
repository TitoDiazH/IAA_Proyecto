from __future__ import annotations

from io import BytesIO
import logging
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import CourseGroup, Syllabus
from app.services.analysis_queue import enqueue_report_analysis
from app.services.filename_parser import FilenameParseError, normalize_course_name, parse_syllabus_filename, slugify_filename
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


def _process_pdf_entries(db: Session, entries: list[tuple[str, bytes]], user_id: str) -> dict:
    """Shared processing for syllabus PDFs, whether they came from inside a ZIP
    or were uploaded directly: parse the filename, extract text, store the PDF,
    create the Syllabus/CourseGroup rows and queue one analysis per course.
    """

    accepted = 0
    rejected: list[dict[str, str]] = []
    course_ids: set[int] = set()
    queued_report_ids: list[int] = []
    uploaded_paths: list[str] = []

    try:
        for original_name, raw_pdf in entries:
            try:
                parsed = parse_syllabus_filename(original_name)
            except FilenameParseError as exc:
                rejected.append({"filename": original_name, "reason": str(exc)})
                continue

            safe_name = slugify_filename(original_name)
            object_key = f"{parsed.academic_period}/{parsed.course_code}/{uuid4().hex}_{safe_name}"

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

    # Fetch affected course groups so the frontend can show cards immediately
    affected_groups = (
        db.query(CourseGroup)
        .options(selectinload(CourseGroup.syllabi), selectinload(CourseGroup.reports))
        .filter(CourseGroup.id.in_(sorted(course_ids)))
        .all()
    )
    courses_data = []
    for group in sorted(affected_groups, key=lambda g: (g.academic_period, g.course_code)):
        latest = max(group.reports, key=lambda r: r.created_at) if group.reports else None
        courses_data.append({
            "id": group.id,
            "academic_period": group.academic_period,
            "year": group.year,
            "term": group.term,
            "career": group.career,
            "course_code": group.course_code,
            "course_name": normalize_course_name(group.course_name),
            "syllabus_count": len(group.syllabi),
            "latest_report_id": latest.id if latest else None,
            "latest_report_status": latest.status if latest else None,
            "latest_report_inconsistency_count": None,
            "created_at": group.created_at,
            "updated_at": group.updated_at,
        })

    return {
        "accepted_count": accepted,
        "rejected_count": len(rejected),
        "rejected_files": rejected,
        "course_ids": sorted(course_ids),
        "courses": courses_data,
        "queued_report_ids": queued_report_ids,
        "message": f"Se cargaron {accepted} syllabus PDF y se encolaron {len(queued_report_ids)} análisis",
    }


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

    entries: list[tuple[str, bytes]] = []
    with archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            original_name = Path(member.filename).name
            if not original_name:
                continue
            entries.append((original_name, archive.read(member)))

    return _process_pdf_entries(db, entries, user_id)


def process_pdf_uploads(db: Session, files: list[tuple[str, bytes]], user_id: str) -> dict:
    """Same pipeline as process_zip_upload, for PDFs uploaded directly (not
    inside a ZIP). Filenames still need to follow the syllabus naming
    convention, since that's the only source of course/NRC/period metadata.
    """

    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024

    entries: list[tuple[str, bytes]] = []
    rejected: list[dict[str, str]] = []
    for filename, content in files:
        if len(content) > max_bytes:
            rejected.append({"filename": filename, "reason": f"El PDF supera {settings.max_upload_mb} MB"})
            continue
        entries.append((filename, content))

    result = _process_pdf_entries(db, entries, user_id)
    result["rejected_files"] = rejected + result["rejected_files"]
    result["rejected_count"] = len(result["rejected_files"])
    return result
