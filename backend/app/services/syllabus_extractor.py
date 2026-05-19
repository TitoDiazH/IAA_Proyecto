from __future__ import annotations

from typing import Any

from app.models import Syllabus
from app.services.ai_client import AIProviderError, JsonCompletionClient
from app.services.pdf_extractor import split_pymupdf_page_marked_text
from app.services.syllabus_prompts import (
    SYLLABUS_EXTRACTION_SCHEMA,
    SYLLABUS_EXTRACTION_SYSTEM_PROMPT,
    build_syllabus_extraction_user_prompt,
)


def _trim_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text

    head_chars = int(max_chars * 0.7)
    tail_chars = max_chars - head_chars
    return (
        text[:head_chars]
        + "\n\n[... texto intermedio omitido por límite de contexto ...]\n\n"
        + text[-tail_chars:]
    )


def _fit_pages_for_prompt(pages: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    if not pages:
        return []

    fitted: list[dict[str, Any]] = []
    remaining_budget = max_chars
    remaining_pages = len(pages)

    for page in pages:
        remaining_pages = max(1, remaining_pages)
        page_text = str(page.get("text") or "")
        page_number = int(page.get("page_number") or 0)
        budget = max(300, remaining_budget // remaining_pages)
        trimmed = page_text if len(page_text) <= budget else _trim_text(page_text, budget)
        fitted.append({"page_number": page_number, "text": trimmed})
        remaining_budget -= len(trimmed)
        remaining_pages -= 1

    return fitted


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _normalize_page_numbers(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []

    page_numbers: list[int] = []
    for value in values:
        try:
            page_number = int(value)
        except (TypeError, ValueError):
            continue
        if page_number > 0:
            page_numbers.append(page_number)
    return sorted(set(page_numbers))


def _section_warning(section_name: str, field_name: str | None = None) -> str:
    if field_name:
        return f"No se pudo determinar {section_name}.{field_name}."
    return f"No se pudo determinar información suficiente para {section_name}."


def _collect_missing_fields(structured_data: dict[str, Any] | None, section_key: str) -> list[str]:
    if not isinstance(structured_data, dict):
        return []

    warnings: list[str] = []

    if section_key == "evaluaciones_y_ponderaciones":
        evaluations = structured_data.get("evaluations")
        if not isinstance(evaluations, list) or not evaluations:
            warnings.append(_section_warning(section_key, "evaluations"))
        else:
            for index, item in enumerate(evaluations, start=1):
                if not isinstance(item, dict):
                    warnings.append(_section_warning(section_key, f"evaluations[{index}]"))
                    continue
                for field in ("type", "quantity", "weight_total", "weight_each", "description"):
                    if item.get(field) is None:
                        warnings.append(_section_warning(section_key, f"evaluations[{index}].{field}"))
    elif section_key == "requisitos_aprobacion":
        for field in ("minimum_final_grade", "minimum_exam_grade"):
            if structured_data.get(field) is None:
                warnings.append(_section_warning(section_key, field))
    elif section_key == "criterios_eximicion":
        for field in ("is_available", "threshold"):
            if structured_data.get(field) is None:
                warnings.append(_section_warning(section_key, field))
    elif section_key == "nota_final":
        for field in ("presentation_grade_formula", "final_grade_formula", "presentation_weight", "exam_weight"):
            if structured_data.get(field) is None:
                warnings.append(_section_warning(section_key, field))

    return warnings


def _normalize_section(section_key: str, raw_section: Any) -> tuple[dict[str, Any], list[str]]:
    section = raw_section if isinstance(raw_section, dict) else {}
    found = bool(section.get("found"))
    page_numbers = _normalize_page_numbers(section.get("page_numbers")) if found else []
    raw_evidence = _normalize_scalar(section.get("raw_evidence")) if found else None
    structured_data = section.get("structured_data") if found else None
    if structured_data is not None and not isinstance(structured_data, dict):
        structured_data = None

    warnings = _collect_missing_fields(structured_data, section_key) if found else []

    normalized = {
        "found": found,
        "page_numbers": page_numbers,
        "raw_evidence": raw_evidence,
        "structured_data": structured_data,
    }

    if not found:
        normalized = {"found": False, "page_numbers": [], "raw_evidence": None, "structured_data": None}

    return normalized, warnings


def _normalize_extraction_result(
    *,
    syllabus: Syllabus,
    raw_result: dict[str, Any],
) -> dict[str, Any]:
    metadata = raw_result.get("metadata") if isinstance(raw_result.get("metadata"), dict) else {}
    raw_sections = raw_result.get("sections") if isinstance(raw_result.get("sections"), dict) else {}

    section_map: dict[str, Any] = {}
    warnings: list[str] = []

    for section_key in (
        "evaluaciones_y_ponderaciones",
        "requisitos_aprobacion",
        "criterios_eximicion",
        "nota_final",
    ):
        normalized_section, section_warnings = _normalize_section(section_key, raw_sections.get(section_key))
        section_map[section_key] = normalized_section
        warnings.extend(section_warnings)

    normalized_warnings = []
    for warning in [*warnings, *list(raw_result.get("warnings", []))]:
        warning_text = str(warning).strip()
        if warning_text and warning_text not in normalized_warnings:
            normalized_warnings.append(warning_text)

    return {
        "metadata": {
            "course_code": _normalize_scalar(metadata.get("course_code")) or syllabus.course_code,
            "course_name": _normalize_scalar(metadata.get("course_name")) or syllabus.course_name,
            "nrc": _normalize_scalar(metadata.get("nrc")) or syllabus.nrc,
            "semester": _normalize_scalar(metadata.get("semester")) or syllabus.academic_period,
            "academic_period": _normalize_scalar(metadata.get("academic_period")) or syllabus.academic_period,
            "source_file": syllabus.original_filename,
        },
        "sections": section_map,
        "warnings": normalized_warnings,
    }


def extract_normalized_syllabus_json(
    syllabus: Syllabus,
    ai_client: JsonCompletionClient,
    max_text_chars: int,
) -> dict[str, Any]:
    pages = split_pymupdf_page_marked_text(syllabus.text_content or "")
    fitted_pages = _fit_pages_for_prompt(pages, max_text_chars)
    prompt = build_syllabus_extraction_user_prompt(
        syllabus_metadata={
            "course_code": syllabus.course_code,
            "course_name": syllabus.course_name,
            "nrc": syllabus.nrc,
            "semester": syllabus.academic_period,
            "academic_period": syllabus.academic_period,
            "source_file": syllabus.original_filename,
        },
        pages=fitted_pages,
    )

    try:
        raw_result = ai_client.complete_json(
            system_prompt=SYLLABUS_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=prompt,
            schema_name="syllabus_extraction",
            schema=SYLLABUS_EXTRACTION_SCHEMA,
        )
    except AIProviderError:
        raise

    if not isinstance(raw_result, dict):
        raise AIProviderError("La extracción estructurada del syllabus no devolvió un JSON válido.")

    return _normalize_extraction_result(syllabus=syllabus, raw_result=raw_result)