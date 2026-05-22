from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import AnalysisReport, CourseGroup, Syllabus
from app.schemas import CourseDetail, CourseListItem, ReportRead, SyllabusRead
from app.services.ai_client import AIConfigurationError, AIProviderError
from app.services.filename_parser import normalize_course_name
from app.services.report_service import analyze_course


router = APIRouter(prefix="/api/courses", tags=["courses"])


def _latest_report(group: CourseGroup) -> AnalysisReport | None:
    if not group.reports:
        return None
    return max(group.reports, key=lambda report: report.created_at)


@router.get("", response_model=list[CourseListItem])
def list_courses(db: Session = Depends(get_db)) -> list[CourseListItem]:
    groups = (
        db.query(CourseGroup)
        .options(selectinload(CourseGroup.syllabi), selectinload(CourseGroup.reports))
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
    )


@router.post("/{course_id}/analyze", response_model=ReportRead)
def analyze_course_endpoint(course_id: int, db: Session = Depends(get_db)) -> AnalysisReport:
    try:
        report = analyze_course(db, course_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AIConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
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


@router.get("/syllabi/{syllabus_id}/download")
def download_syllabus(syllabus_id: int, db: Session = Depends(get_db)) -> FileResponse:
    syllabus = db.query(Syllabus).filter(Syllabus.id == syllabus_id).one_or_none()
    if syllabus is None:
        raise HTTPException(status_code=404, detail="Syllabus no encontrado")

    path = Path(syllabus.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="El archivo PDF ya no existe en almacenamiento")

    return FileResponse(path, filename=syllabus.original_filename, media_type="application/pdf")


@router.get("/syllabi/{syllabus_id}/view")
def view_syllabus(syllabus_id: int, db: Session = Depends(get_db)) -> FileResponse:
    syllabus = db.query(Syllabus).filter(Syllabus.id == syllabus_id).one_or_none()
    if syllabus is None:
        raise HTTPException(status_code=404, detail="Syllabus no encontrado")

    path = Path(syllabus.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="El archivo PDF ya no existe en almacenamiento")

    return FileResponse(
        path,
        filename=syllabus.original_filename,
        media_type="application/pdf",
        content_disposition_type="inline",
    )
