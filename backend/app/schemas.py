from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RejectedFile(BaseModel):
    filename: str
    reason: str


class SyllabusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    file_size: int
    academic_period: str
    year: int
    term: str
    career: str
    course_code: str
    nrc: str
    course_name: str
    extraction_status: str
    extraction_error: str | None
    created_at: datetime


class CourseListItem(BaseModel):
    id: int
    academic_period: str
    year: int
    term: str
    career: str
    course_code: str
    course_name: str
    syllabus_count: int
    latest_report_id: int | None = None
    latest_report_status: str | None = None
    latest_report_inconsistency_count: int | None = None
    created_at: datetime
    updated_at: datetime


class CourseDetail(BaseModel):
    id: int
    academic_period: str
    year: int
    term: str
    career: str
    course_code: str
    course_name: str
    syllabi: list[SyllabusRead]
    latest_report_id: int | None = None
    latest_report_status: str | None = None


class InconsistencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    section: str
    variable: str
    difference: str
    involved_nrcs: list[str]
    severity: str
    suggestion: str
    evidence: Any
    created_at: datetime


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_group_id: int
    status: str
    compared_nrcs: list[str]
    summary: dict[str, Any]
    processing_time_seconds: float
    created_at: datetime
    inconsistencies: list[InconsistencyRead]


class UploadResponse(BaseModel):
    accepted_count: int
    rejected_count: int
    rejected_files: list[RejectedFile]
    course_ids: list[int]
    queued_report_ids: list[int] = []
    message: str
