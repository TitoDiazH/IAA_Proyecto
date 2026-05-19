from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import AnalysisReport
from app.schemas import ReportRead


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{report_id}", response_model=ReportRead)
def get_report(report_id: int, db: Session = Depends(get_db)) -> AnalysisReport:
    report = (
        db.query(AnalysisReport)
        .options(selectinload(AnalysisReport.inconsistencies))
        .filter(AnalysisReport.id == report_id)
        .one_or_none()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return report

