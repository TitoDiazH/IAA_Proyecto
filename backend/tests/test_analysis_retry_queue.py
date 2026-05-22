import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AnalysisReport, CourseGroup, Syllabus
from app.services.report_service import analyze_course, mark_report_queued_after_error


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_course(db):
    course = CourseGroup(
        academic_period="202610",
        year=2026,
        term="10",
        course_code="2207",
        career="ING",
        course_name="Termodinamica",
    )
    db.add(course)
    db.flush()
    return course


def test_failed_analysis_requeues_three_times_then_fails():
    db = make_session()
    course = make_course(db)
    report = AnalysisReport(
        course_group_id=course.id,
        status="processing",
        compared_nrcs=[],
        summary={},
        processing_time_seconds=0,
    )
    db.add(report)
    db.commit()

    for expected_retry_count in [1, 2, 3]:
        assert mark_report_queued_after_error(db, report.id, "boom", max_retries=3)
        db.refresh(report)
        assert report.status == "queued"
        assert report.summary["retry_count"] == expected_retry_count

    assert not mark_report_queued_after_error(db, report.id, "boom again", max_retries=3)
    db.refresh(report)
    assert report.status == "failed"
    assert report.summary["retry_count"] == 3
    assert report.summary["last_error"] == "boom again"


def test_processing_state_preserves_retry_count_when_analysis_fails(monkeypatch):
    db = make_session()
    course = make_course(db)
    report = AnalysisReport(
        course_group_id=course.id,
        status="queued",
        compared_nrcs=[],
        summary={"retry_count": 2, "max_retries": 3},
        processing_time_seconds=0,
    )
    syllabi = [
        Syllabus(
            course_group_id=course.id,
            original_filename=f"202610-ING-2207-NRC-{nrc}-TERMODINAMICA.pdf",
            stored_path=f"/tmp/{nrc}.pdf",
            file_size=10,
            academic_period="202610",
            year=2026,
            term="10",
            career="ING",
            course_code="2207",
            nrc=nrc,
            course_name="Termodinamica",
            text_content="texto",
            extraction_status="ok",
        )
        for nrc in ["7542", "7543"]
    ]
    db.add(report)
    db.add_all(syllabi)
    db.commit()

    monkeypatch.setattr(
        "app.services.report_service.analyze_syllabi",
        lambda syllabi, course_metadata: (_ for _ in ()).throw(RuntimeError("provider down")),
    )

    with pytest.raises(RuntimeError, match="provider down"):
        analyze_course(db, course.id, report_id=report.id)

    db.refresh(report)
    assert report.status == "processing"
    assert report.summary["retry_count"] == 2
    assert report.summary["max_retries"] == 3
