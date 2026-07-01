from __future__ import annotations

from collections import Counter, defaultdict
import re
import unicodedata
from typing import Any

from app.services.ai_client import AIProviderError, JsonCompletionClient
from app.services.citation_resolver import build_source_index, map_section_label, resolve_evidence_item
from app.services.filename_parser import normalize_course_name
from app.services.syllabus_prompts import (
    SYLLABUS_COMPARISON_SCHEMA,
    SYLLABUS_COMPARISON_SYSTEM_PROMPT,
    build_syllabus_comparison_user_prompt,
)


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (int, float)):
        return value
    return None if value is None else str(value)


def _normalize_text_equivalence(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [
        token
        for token in text.split()
        if token
        not in {
            "a",
            "an",
            "and",
            "by",
            "de",
            "del",
            "e",
            "el",
            "en",
            "es",
            "for",
            "from",
            "la",
            "las",
            "lo",
            "los",
            "of",
            "o",
            "or",
            "para",
            "por",
            "the",
            "to",
            "un",
            "una",
            "unos",
            "unas",
            "y",
        }
    ]
    return " ".join(tokens).strip()


def _normalize_severity(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace("í", "i")
    if normalized.startswith("cr"):
        return "critica"
    if normalized.startswith("me"):
        return "menor"
    return "moderada"


def _normalize_evidence_items(
    items: Any,
    sources_by_nrc: dict[str, list[dict[str, Any]]] | None = None,
    expected_section: str | None = None,
) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized_items

    source_index = sources_by_nrc or {}
    for item in items:
        if not isinstance(item, dict):
            continue
        resolved = resolve_evidence_item(item, source_index, expected_section)
        if resolved is None:
            continue
        normalized_items.append(resolved)
    return normalized_items


def _majority_value(values_by_nrc: dict[str, Any]) -> Any:
    values = [_normalize_scalar(value) for value in values_by_nrc.values() if _normalize_scalar(value) is not None]
    if not values:
        return None
    most_common = Counter(values).most_common(1)[0][0]
    return most_common


def _most_deviating_nrc(outlier_counts: dict[str, int]) -> tuple[str | None, int]:
    if not outlier_counts:
        return None, 0
    nrc, count = max(outlier_counts.items(), key=lambda item: (item[1], item[0]))
    return (nrc if count > 0 else None), count


def _is_equivalent_alert(item: dict[str, Any]) -> bool:
    values_by_nrc = item.get("values_by_nrc") or {}
    if not isinstance(values_by_nrc, dict) or len(values_by_nrc) < 2:
        return False

    normalized_values = []
    for value in values_by_nrc.values():
        scalar = _normalize_scalar(value)
        if scalar is None:
            continue
        if isinstance(scalar, str):
            normalized_values.append(_normalize_text_equivalence(scalar))
        else:
            normalized_values.append(str(scalar))

    normalized_values = [value for value in normalized_values if value]
    if len(normalized_values) < 2:
        return False

    if len(set(normalized_values)) == 1:
        return True

    description = _normalize_text_equivalence(item.get("description") or item.get("difference"))
    if description:
        # If the model only rephrased the same rule/value for every NRC, treat it as noise.
        common_description = all(
            _normalize_text_equivalence(value) == description for value in values_by_nrc.values() if value is not None
        )
        if common_description:
            return True

    return False


def _normalize_comparison_result(
    *,
    course_metadata: dict[str, Any],
    normalized_syllabi: dict[str, Any],
    raw_result: dict[str, Any],
) -> dict[str, Any]:
    nrcs = list(normalized_syllabi.keys())
    course = raw_result.get("course") if isinstance(raw_result.get("course"), dict) else {}
    course_code = _normalize_scalar(course.get("course_code")) or course_metadata.get("course_code")
    course_name = normalize_course_name(
        _normalize_scalar(course.get("course_name")) or course_metadata.get("course_name")
    )
    compared_nrcs = [str(nrc) for nrc in course.get("nrcs_compared", []) if str(nrc).strip()] or nrcs

    raw_summary = raw_result.get("summary") if isinstance(raw_result.get("summary"), dict) else {}
    raw_inconsistencies = raw_result.get("inconsistencies") if isinstance(raw_result.get("inconsistencies"), list) else []

    normalized_inconsistencies: list[dict[str, Any]] = []
    severity_counts = {"critica": 0, "moderada": 0, "menor": 0}
    outlier_counts: dict[str, int] = defaultdict(int)
    sources_by_nrc = build_source_index(normalized_syllabi)

    for item in raw_inconsistencies:
        if not isinstance(item, dict):
            continue

        values_by_nrc = {
            str(nrc): _normalize_scalar(value)
            for nrc, value in (item.get("values_by_nrc") or {}).items()
            if str(nrc).strip()
        }
        if not values_by_nrc:
            continue

        if _is_equivalent_alert({**item, "values_by_nrc": values_by_nrc}):
            continue

        severity = _normalize_severity(item.get("severity"))
        description = str(item.get("description") or item.get("difference") or "").strip()
        majority_value = _normalize_scalar(item.get("majority_value"))
        if majority_value is None:
            majority_value = _majority_value(values_by_nrc)

        outlier_nrcs = [str(nrc) for nrc in item.get("outlier_nrcs", []) if str(nrc).strip()]
        if not outlier_nrcs and majority_value is not None:
            outlier_nrcs = [nrc for nrc, value in values_by_nrc.items() if value is not None and value != majority_value]

        evidence = _normalize_evidence_items(
            item.get("evidence"), sources_by_nrc, map_section_label(item.get("section"))
        )

        normalized_item = {
            "section": str(item.get("section") or "Apartado no especificado").strip(),
            "variable": str(item.get("variable") or "Variable no especificada").strip(),
            "severity": severity,
            "description": description,
            "values_by_nrc": values_by_nrc,
            "majority_value": majority_value,
            "outlier_nrcs": outlier_nrcs,
            "evidence": evidence,
            "suggested_action": str(item.get("suggested_action") or item.get("suggestion") or "").strip(),
        }
        normalized_inconsistencies.append(normalized_item)
        severity_counts[severity] += 1
        for nrc in outlier_nrcs:
            outlier_counts[nrc] += 1

    summary = raw_summary if isinstance(raw_summary, dict) else {}
    most_deviating_nrc, alerts = _most_deviating_nrc(outlier_counts)
    raw_possible_outlier = summary.get("possible_outlier") if isinstance(summary.get("possible_outlier"), dict) else {}
    possible_outlier = {
        "nrc": _normalize_scalar(raw_possible_outlier.get("nrc")) or most_deviating_nrc,
        "alerts": int(raw_possible_outlier.get("alerts", alerts)) if raw_possible_outlier else alerts,
        "reason": _normalize_scalar(raw_possible_outlier.get("reason")) if raw_possible_outlier else ("Acumula más diferencias detectadas entre apartados." if alerts else None),
    }
    if not possible_outlier["nrc"]:
        possible_outlier["nrc"] = most_deviating_nrc
    if not possible_outlier["alerts"]:
        possible_outlier["alerts"] = alerts
    if possible_outlier["reason"] is None and alerts:
        possible_outlier["reason"] = "Acumula más diferencias detectadas entre apartados."

    severity_counts_payload = {
        "Crítica": severity_counts["critica"],
        "Moderada": severity_counts["moderada"],
        "Menor": severity_counts["menor"],
    }

    summary_payload = {
        "course": {
            "course_code": course_code,
            "course_name": course_name,
            "nrcs_compared": compared_nrcs,
        },
        "total_syllabus_compared": int(summary.get("total_syllabus_compared", len(nrcs))) if nrcs else 0,
        "total_inconsistencies": len(normalized_inconsistencies),
        "most_deviating_nrc": most_deviating_nrc or _normalize_scalar(summary.get("most_deviating_nrc")),
        "severity_counts": severity_counts_payload,
        "possible_outlier": possible_outlier,
        "analysis_mode": str(summary.get("analysis_mode") or "group_pattern"),
        "warnings": [str(item).strip() for item in raw_result.get("warnings", []) if str(item).strip()],
    }

    return {
        "course": summary_payload["course"],
        "summary": summary_payload,
        "inconsistencies": normalized_inconsistencies,
        "warnings": summary_payload["warnings"],
    }


def compare_normalized_syllabi(
    *,
    course_metadata: dict[str, Any],
    normalized_syllabi_by_nrc: dict[str, Any],
    ai_client: JsonCompletionClient,
) -> dict[str, Any]:
    prompt = build_syllabus_comparison_user_prompt(
        course_metadata=course_metadata,
        normalized_syllabi=list(normalized_syllabi_by_nrc.values()),
    )

    try:
        raw_result = ai_client.complete_json(
            system_prompt=SYLLABUS_COMPARISON_SYSTEM_PROMPT,
            user_prompt=prompt,
            schema_name="syllabus_comparison",
            schema=SYLLABUS_COMPARISON_SCHEMA,
        )
    except AIProviderError:
        raise

    if not isinstance(raw_result, dict):
        raise AIProviderError("La comparación global de syllabus no devolvió un JSON válido.")

    return _normalize_comparison_result(
        course_metadata=course_metadata,
        normalized_syllabi=normalized_syllabi_by_nrc,
        raw_result=raw_result,
    )
