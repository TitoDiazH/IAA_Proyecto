from __future__ import annotations

import time

from sqlalchemy.orm import Session, selectinload

from app.models import AnalysisReport, CourseGroup, Inconsistency, Syllabus
from app.services.ai_analyzer import analyze_syllabi
from app.services.filename_parser import normalize_course_name


def analyze_course(db: Session, course_id: int) -> AnalysisReport:
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

    if len(syllabi) < 2:
        report = AnalysisReport(
            course_group_id=course.id,
            status="completed",
            compared_nrcs=[syllabus.nrc for syllabus in syllabi],
            summary={
                "course": {
                    "academic_period": course.academic_period,
                    "course_code": course.course_code,
                    "course_name": course_name,
                },
                "analysis_provider": "gemini",
                "message": "Se requiere al menos dos syllabus para comparar un curso.",
                "compared_count": len(syllabi),
                "severity_counts": {},
            },
            processing_time_seconds=round(time.perf_counter() - started_at, 3),
        )
        db.add(report)
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

    report = AnalysisReport(
        course_group_id=course.id,
        status="completed",
        compared_nrcs=comparison["compared_nrcs"],
        summary=summary,
        processing_time_seconds=elapsed,
    )
    db.add(report)
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
