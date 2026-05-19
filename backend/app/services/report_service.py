from __future__ import annotations

import time

from sqlalchemy.orm import Session, selectinload

from app.models import AnalysisReport, CourseGroup, Inconsistency, Syllabus
from app.services.ai_analyzer import analyze_syllabi_with_ai


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
                    "course_name": course.course_name,
                },
                "analysis_provider": "ollama",
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
        "course_name": course.course_name,
    }
    comparison = analyze_syllabi_with_ai(syllabi, course_metadata)
    elapsed = round(time.perf_counter() - started_at, 3)
    summary = comparison["summary"]
    summary["course"] = course_metadata

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
        db.add(
            Inconsistency(
                report_id=report.id,
                section=item["section"],
                variable=item["variable"],
                difference=item["difference"],
                involved_nrcs=item["involved_nrcs"],
                severity=item["severity"],
                suggestion=item["suggestion"],
                evidence=item["evidence"],
            )
        )

    db.commit()
    db.refresh(report)
    return report
