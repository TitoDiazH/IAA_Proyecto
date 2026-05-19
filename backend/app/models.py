from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class CourseGroup(Base):
    __tablename__ = "course_groups"
    __table_args__ = (
        UniqueConstraint("academic_period", "course_code", name="uq_course_group_period_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    academic_period = Column(String(6), index=True, nullable=False)
    year = Column(Integer, index=True, nullable=False)
    term = Column(String(2), index=True, nullable=False)
    course_code = Column(String(80), index=True, nullable=False)
    career = Column(String(80), nullable=False)
    course_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    syllabi = relationship("Syllabus", back_populates="course_group", cascade="all, delete-orphan")
    reports = relationship("AnalysisReport", back_populates="course_group", cascade="all, delete-orphan")


class Syllabus(Base):
    __tablename__ = "syllabi"

    id = Column(Integer, primary_key=True, index=True)
    course_group_id = Column(Integer, ForeignKey("course_groups.id"), nullable=False, index=True)
    original_filename = Column(String(500), nullable=False)
    stored_path = Column(String(1000), nullable=False)
    file_size = Column(Integer, nullable=False)
    academic_period = Column(String(6), index=True, nullable=False)
    year = Column(Integer, index=True, nullable=False)
    term = Column(String(2), index=True, nullable=False)
    career = Column(String(80), nullable=False)
    course_code = Column(String(80), nullable=False)
    nrc = Column(String(80), index=True, nullable=False)
    course_name = Column(String(255), nullable=False)
    text_content = Column(Text, nullable=True)
    extraction_status = Column(String(40), default="ok", nullable=False)
    extraction_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    course_group = relationship("CourseGroup", back_populates="syllabi")


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id = Column(Integer, primary_key=True, index=True)
    course_group_id = Column(Integer, ForeignKey("course_groups.id"), nullable=False, index=True)
    status = Column(String(40), default="completed", nullable=False)
    compared_nrcs = Column(JSON, default=list, nullable=False)
    summary = Column(JSON, default=dict, nullable=False)
    processing_time_seconds = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    course_group = relationship("CourseGroup", back_populates="reports")
    inconsistencies = relationship(
        "Inconsistency", back_populates="report", cascade="all, delete-orphan"
    )


class Inconsistency(Base):
    __tablename__ = "inconsistencies"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("analysis_reports.id"), nullable=False, index=True)
    section = Column(String(180), nullable=False)
    variable = Column(String(180), nullable=False)
    difference = Column(Text, nullable=False)
    involved_nrcs = Column(JSON, default=list, nullable=False)
    severity = Column(String(40), nullable=False)
    suggestion = Column(Text, nullable=False)
    evidence = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    report = relationship("AnalysisReport", back_populates="inconsistencies")

