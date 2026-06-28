from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import AnalysisReport, CourseGroup
from app.schemas import ReportRead


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{report_id}", response_model=ReportRead)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AnalysisReport:
    report = (
        db.query(AnalysisReport)
        .join(CourseGroup, AnalysisReport.course_group_id == CourseGroup.id)
        .options(selectinload(AnalysisReport.inconsistencies))
        .filter(AnalysisReport.id == report_id, CourseGroup.user_id == current_user["id"])
        .one_or_none()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return report

