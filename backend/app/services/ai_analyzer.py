from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.models import Syllabus
from app.services.ai_client import JsonCompletionClient, get_json_client
from app.services.syllabus_comparator import compare_normalized_syllabi
from app.services.syllabus_extractor import extract_normalized_syllabus_json


def analyze_syllabi_with_ai(
    syllabi: list[Syllabus],
    course_metadata: dict[str, Any],
    client: JsonCompletionClient | None = None,
    max_text_chars: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    ai_client = client or get_json_client()
    text_limit = max_text_chars or settings.ai_max_pdf_text_chars

    extracted_by_nrc: dict[str, Any] = {}
    for syllabus in syllabi:
        extracted_by_nrc[syllabus.nrc] = extract_normalized_syllabus_json(
            syllabus,
            ai_client,
            text_limit,
        )

    comparison = compare_normalized_syllabi(
        course_metadata=course_metadata,
        normalized_syllabi_by_nrc=extracted_by_nrc,
        ai_client=ai_client,
    )

    return {
        "course": comparison["course"],
        "compared_nrcs": comparison["course"]["nrcs_compared"],
        "summary": comparison["summary"],
        "inconsistencies": comparison["inconsistencies"],
        "warnings": comparison["warnings"],
        "normalized_syllabi_by_nrc": extracted_by_nrc,
    }