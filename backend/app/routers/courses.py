import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import AnalysisReport, CourseGroup, Syllabus
from app.schemas import CourseDetail, CourseListItem, ReportRead, SyllabusRead
from app.services.analysis_queue import enqueue_report_analysis
from app.services.filename_parser import normalize_course_name
from app.services.report_service import create_queued_analysis_report
from app.services.storage_service import StorageError, download_pdf


router = APIRouter(prefix="/api/courses", tags=["courses"])
logger = logging.getLogger(__name__)


def _latest_report(group: CourseGroup) -> AnalysisReport | None:
    if not group.reports:
        return None
    return max(group.reports, key=lambda report: report.created_at)


@router.get("", response_model=list[CourseListItem])
def list_courses(db: Session = Depends(get_db)) -> list[CourseListItem]:
    groups = (
        db.query(CourseGroup)
        .options(
            selectinload(CourseGroup.syllabi),
            selectinload(CourseGroup.reports).selectinload(AnalysisReport.inconsistencies),
        )
        .order_by(CourseGroup.academic_period.desc(), CourseGroup.course_code.asc())
        .all()
    )
    response: list[CourseListItem] = []
    for group in groups:
        latest = _latest_report(group)
        response.append(
            CourseListItem(
                id=group.id,
                academic_period=group.academic_period,
                year=group.year,
                term=group.term,
                career=group.career,
                course_code=group.course_code,
                course_name=normalize_course_name(group.course_name),
                syllabus_count=len(group.syllabi),
                latest_report_id=latest.id if latest else None,
                latest_report_status=latest.status if latest else None,
                latest_report_inconsistency_count=(
                    len(latest.inconsistencies) if latest and latest.status == "completed" else None
                ),
                created_at=group.created_at,
                updated_at=group.updated_at,
            )
        )
    return response


@router.get("/{course_id}", response_model=CourseDetail)
def get_course(course_id: int, db: Session = Depends(get_db)) -> CourseDetail:
    group = (
        db.query(CourseGroup)
        .options(selectinload(CourseGroup.syllabi), selectinload(CourseGroup.reports))
        .filter(CourseGroup.id == course_id)
        .one_or_none()
    )
    if group is None:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    latest = _latest_report(group)
    syllabi = sorted(group.syllabi, key=lambda syllabus: syllabus.nrc)
    return CourseDetail(
        id=group.id,
        academic_period=group.academic_period,
        year=group.year,
        term=group.term,
        career=group.career,
        course_code=group.course_code,
        course_name=normalize_course_name(group.course_name),
        syllabi=[SyllabusRead.model_validate(syllabus) for syllabus in syllabi],
        latest_report_id=latest.id if latest else None,
        latest_report_status=latest.status if latest else None,
    )


@router.post("/{course_id}/analyze", response_model=ReportRead)
def analyze_course_endpoint(course_id: int, db: Session = Depends(get_db)) -> AnalysisReport:
    try:
        report = create_queued_analysis_report(db, course_id)
        db.commit()
        db.refresh(report)
        enqueue_report_analysis(report.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return report


@router.get("/{course_id}/report/latest", response_model=ReportRead)
def latest_course_report(course_id: int, db: Session = Depends(get_db)) -> AnalysisReport:
    report = (
        db.query(AnalysisReport)
        .options(selectinload(AnalysisReport.inconsistencies))
        .filter(AnalysisReport.course_group_id == course_id)
        .order_by(AnalysisReport.created_at.desc())
        .first()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Este curso aún no tiene reportes")
    return report


def _pdf_response(syllabus: Syllabus, disposition: str) -> Response:
    try:
        content = download_pdf(syllabus.stored_path)
    except StorageError as exc:
        logger.warning("Could not retrieve syllabus %s: %s", syllabus.id, exc)
        raise HTTPException(
            status_code=502,
            detail="No se pudo recuperar el PDF desde el almacenamiento",
        ) from exc

    encoded_filename = quote(syllabus.original_filename, safe="")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{encoded_filename}",
            "Content-Length": str(len(content)),
        },
    )


@router.get("/syllabi/{syllabus_id}/download")
def download_syllabus(syllabus_id: int, db: Session = Depends(get_db)) -> Response:
    syllabus = db.query(Syllabus).filter(Syllabus.id == syllabus_id).one_or_none()
    if syllabus is None:
        raise HTTPException(status_code=404, detail="Syllabus no encontrado")

    return _pdf_response(syllabus, "attachment")


@router.get("/syllabi/{syllabus_id}/view")
def view_syllabus(syllabus_id: int, db: Session = Depends(get_db)) -> Response:
    syllabus = db.query(Syllabus).filter(Syllabus.id == syllabus_id).one_or_none()
    if syllabus is None:
        raise HTTPException(status_code=404, detail="Syllabus no encontrado")

    return _pdf_response(syllabus, "inline")
