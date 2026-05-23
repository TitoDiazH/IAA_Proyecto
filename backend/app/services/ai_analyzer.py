from __future__ import annotations

from typing import Any

from app.models import Syllabus
from app.services.conditions_formula_extractor import enrich_syllabi_with_conditions_export
from app.services.ai_client import JsonCompletionClient, get_json_client
from app.services.syllabus_comparator import compare_normalized_syllabi
from app.services.syllabus_extractor import extract_normalized_syllabus_json_from_pdf


def analyze_syllabi(
    syllabi: list[Syllabus],
    course_metadata: dict[str, Any],
    client: JsonCompletionClient | None = None,
) -> dict[str, Any]:
    ai_client = client or get_json_client()

    extracted_by_nrc: dict[str, Any] = {}
    for syllabus in syllabi:
        extracted_by_nrc[syllabus.nrc] = extract_normalized_syllabus_json_from_pdf(syllabus)

    comparison = compare_normalized_syllabi(
        course_metadata=course_metadata,
        normalized_syllabi_by_nrc=extracted_by_nrc,
        ai_client=ai_client,
    )

    try:
        extracted_by_nrc = enrich_syllabi_with_conditions_export(extracted_by_nrc, ai_client)
    except Exception:
        # The export table should improve when the model extracts formulas, but
        # a provider/schema issue here should not block the main consistency report.
        pass

    return {
        "course": comparison["course"],
        "compared_nrcs": comparison["course"]["nrcs_compared"],
        "summary": comparison["summary"],
        "inconsistencies": comparison["inconsistencies"],
        "warnings": comparison["warnings"],
        "normalized_syllabi_by_nrc": extracted_by_nrc,
    }
