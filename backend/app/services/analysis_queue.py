from __future__ import annotations

import logging
import queue
import threading
import time

from app.config import get_settings
from app.database import SessionLocal
from app.models import AnalysisReport
from app.services.ai_client import AIQuotaExceededError
from app.services.report_service import analyze_course, mark_report_queued_after_error


logger = logging.getLogger(__name__)

_work_queue: queue.Queue[int] = queue.Queue()
_started = False
_start_lock = threading.Lock()


def start_analysis_worker() -> None:
    global _started

    with _start_lock:
        if _started:
            return

        worker = threading.Thread(
            target=_run_worker,
            name="analysis-queue-worker",
            daemon=True,
        )
        worker.start()
        _started = True
        _enqueue_existing_pending_reports()


def enqueue_report_analysis(report_id: int) -> None:
    _work_queue.put(report_id)


def requeue_report_analysis(report_id: int, delay_seconds: int | None = None) -> None:
    delay = get_settings().analysis_retry_delay_seconds if delay_seconds is None else delay_seconds
    if delay <= 0:
        enqueue_report_analysis(report_id)
        return

    timer = threading.Timer(delay, enqueue_report_analysis, args=[report_id])
    timer.daemon = True
    timer.start()


def _enqueue_existing_pending_reports() -> None:
    db = SessionLocal()
    try:
        reports = (
            db.query(AnalysisReport)
            .filter(AnalysisReport.status.in_(["queued", "processing"]))
            .order_by(AnalysisReport.created_at.asc())
            .all()
        )
        report_ids = [report.id for report in reports]
        for report in reports:
            report.status = "queued"
        db.commit()
        for report_id in report_ids:
            _work_queue.put(report_id)
    finally:
        db.close()


def _run_worker() -> None:
    while True:
        report_id = _work_queue.get()
        try:
            _process_report(report_id)
        finally:
            _work_queue.task_done()


def _process_report(report_id: int) -> None:
    started_at = time.perf_counter()
    db = SessionLocal()
    try:
        report = db.query(AnalysisReport).filter(AnalysisReport.id == report_id).one_or_none()
        if report is None or report.status != "queued":
            return

        analyze_course(db, report.course_group_id, report_id=report.id)
    except Exception as exc:  # pragma: no cover - defensive background worker path
        logger.exception("Analysis job %s failed", report_id)
        db.rollback()
        error_type = "quota_exceeded" if isinstance(exc, AIQuotaExceededError) else None
        should_requeue = mark_report_queued_after_error(
            db,
            report_id,
            str(exc),
            elapsed=time.perf_counter() - started_at,
            max_retries=get_settings().analysis_max_retries,
            error_type=error_type,
        )
        if should_requeue:
            requeue_report_analysis(report_id)
    finally:
        db.close()
