from __future__ import annotations

import time

from sqlalchemy.orm import Session, selectinload

from app.models import AnalysisReport, CourseGroup, Inconsistency, Syllabus
from app.services.ai_analyzer import analyze_syllabi
from app.services.filename_parser import normalize_course_name


def create_queued_analysis_report(db: Session, course_id: int) -> AnalysisReport:
    course = db.query(CourseGroup).filter(CourseGroup.id == course_id).one_or_none()
    if course is None:
        raise ValueError("Curso no encontrado")

    report = AnalysisReport(
        course_group_id=course.id,
        status="queued",
        compared_nrcs=[],
        summary={
            "message": "El análisis quedó en cola y se ejecutará automáticamente.",
        },
        processing_time_seconds=0,
    )
    db.add(report)
    db.flush()
    return report


def mark_report_queued_after_error(
    db: Session,
    report_id: int,
    message: str,
    elapsed: float = 0,
    max_retries: int = 3,
) -> bool:
    report = db.query(AnalysisReport).filter(AnalysisReport.id == report_id).one_or_none()
    if report is None:
        return False

    previous_summary = report.summary if isinstance(report.summary, dict) else {}
    retry_count = int(previous_summary.get("retry_count") or 0)

    if retry_count >= max_retries:
        report.status = "failed"
        report.summary = {
            "message": f"El análisis falló después de {max_retries} reintentos automáticos.",
            "last_error": message,
            "retry_count": retry_count,
            "max_retries": max_retries,
            "analysis_provider": "gemini",
        }
    else:
        next_retry_count = retry_count + 1
        report.status = "queued"
        report.summary = {
            "message": "El análisis falló y volvió a la cola automáticamente.",
            "last_error": message,
            "retry_count": next_retry_count,
            "max_retries": max_retries,
            "analysis_provider": "gemini",
        }

    report.processing_time_seconds = round(elapsed, 3)
    db.query(Inconsistency).filter(Inconsistency.report_id == report.id).delete()
    db.commit()
    return report.status == "queued"


def analyze_course(db: Session, course_id: int, report_id: int | None = None) -> AnalysisReport:
    course = (
        db.query(CourseGroup)
        .options(selectinload(CourseGroup.syllabi))
        .filter(CourseGroup.id == course_id)
        .one_or_none()
    )
    if course is None:
        raise ValueError("Curso no encontrado")

    syllabi: list[Syllabus] = sorted(course.syllabi, key=lambda item: item.nrc)
    course_name = normalize_course_name(course.course_name)
    started_at = time.perf_counter()
    report = None

    if report_id is not None:
        report = (
            db.query(AnalysisReport)
            .filter(
                AnalysisReport.id == report_id,
                AnalysisReport.course_group_id == course.id,
            )
            .one_or_none()
        )
        if report is None:
            raise ValueError("Reporte no encontrado")

        previous_summary = report.summary if isinstance(report.summary, dict) else {}
        processing_summary = {
            "message": "Análisis en ejecución.",
            "analysis_provider": "gemini",
        }
        if previous_summary.get("retry_count") is not None:
            processing_summary["retry_count"] = previous_summary["retry_count"]
        if previous_summary.get("max_retries") is not None:
            processing_summary["max_retries"] = previous_summary["max_retries"]

        report.status = "processing"
        report.compared_nrcs = []
        report.summary = processing_summary
        report.processing_time_seconds = 0
        db.query(Inconsistency).filter(Inconsistency.report_id == report.id).delete()
        db.commit()

    if len(syllabi) < 2:
        if report is None:
            report = AnalysisReport(course_group_id=course.id)
            db.add(report)

        report.status = "completed"
        report.compared_nrcs = [syllabus.nrc for syllabus in syllabi]
        report.summary = {
            "course": {
                "academic_period": course.academic_period,
                "course_code": course.course_code,
                "course_name": course_name,
            },
            "analysis_provider": "gemini",
            "message": "Se requiere al menos dos syllabus para comparar un curso.",
            "compared_count": len(syllabi),
            "severity_counts": {},
        }
        report.processing_time_seconds = round(time.perf_counter() - started_at, 3)
        db.commit()
        db.refresh(report)
        return report

    course_metadata = {
        "academic_period": course.academic_period,
        "year": course.year,
        "term": course.term,
        "career": course.career,
        "course_code": course.course_code,
        "course_name": course_name,
    }
    comparison = analyze_syllabi(syllabi, course_metadata)
    elapsed = round(time.perf_counter() - started_at, 3)
    summary = comparison["summary"]
    summary["course"] = comparison.get("course", course_metadata)
    summary["analysis_provider"] = "gemini"
    summary["normalized_syllabi_by_nrc"] = comparison.get("normalized_syllabi_by_nrc", {})

    if report is None:
        report = AnalysisReport(course_group_id=course.id)
        db.add(report)

    report.status = "completed"
    report.compared_nrcs = comparison["compared_nrcs"]
    report.summary = summary
    report.processing_time_seconds = elapsed
    db.flush()

    for item in comparison["inconsistencies"]:
        difference = item.get("difference") or item.get("description") or ""
        suggestion = item.get("suggestion") or item.get("suggested_action") or ""
        evidence = item.get("evidence") or {}
        db.add(
            Inconsistency(
                report_id=report.id,
                section=item["section"],
                variable=item["variable"],
                difference=difference,
                involved_nrcs=item.get("involved_nrcs") or item.get("outlier_nrcs") or list(item.get("values_by_nrc", {}).keys()),
                severity=item["severity"],
                suggestion=suggestion,
                evidence=evidence,
            )
        )

    db.commit()
    db.refresh(report)
    return report
