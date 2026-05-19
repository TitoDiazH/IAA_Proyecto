from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from app.config import get_settings
from app.models import Syllabus
from app.services.ai_client import JsonCompletionClient, get_json_client, AIProviderError
from app.services.ai_prompts import (
    COMPARISON_SCHEMA,
    COMPARISON_SYSTEM_PROMPT,
    SECTION_EXTRACTION_SCHEMA,
    SECTION_EXTRACTION_SYSTEM_PROMPT,
    SECTION_PROMPTS,
    SectionPrompt,
)
from app.services.evaluation_table_extractor import (
    extract_evaluation_table_from_pdf,
    format_weight_map,
)
from app.services.section_extractor import SECTION_DEFINITIONS, extract_sections_from_text


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


def _split_page_blocks(text: str) -> list[tuple[int, str]]:
    pages: list[tuple[int, str]] = []
    current_page = 0
    current_lines: list[str] = []

    for line in text.splitlines():
        match = re.match(r"^--- Página (\d+) ---$", line.strip())
        if match:
            if current_page:
                pages.append((current_page, "\n".join(current_lines).strip()))
            current_page = int(match.group(1))
            current_lines = []
            continue

        current_lines.append(line)

    if current_page:
        pages.append((current_page, "\n".join(current_lines).strip()))

    return pages


def _section_keywords(section_key: str) -> list[str]:
    return {
        "general_info": [
            "informacion general",
            "datos generales",
            "asignatura",
            "carrera",
            "codigo",
            "nrc",
            "creditos",
            "modalidad",
            "semestre",
            "requisitos previos",
        ],
        "evaluations": [
            "evaluacion",
            "evaluaciones",
            "ponderacion",
            "ponderaciones",
            "sistema de evaluacion",
            "instrumentos evaluativos",
        ],
        "approval_requirements": [
            "requisitos de aprobacion",
            "condiciones de aprobacion",
            "aprobacion",
            "reprobacion",
            "asistencia",
        ],
        "exemption": [
            "eximicion",
            "eximirse",
            "exoneracion",
            "eximido",
            "liberacion",
        ],
        "final_grade": [
            "nota final",
            "formula",
            "cálculo de nota final",
            "calculo de nota final",
            "nota de presentacion",
            "nf",
        ],
    }.get(section_key, [])


def _general_info_text(text: str, max_chars: int) -> str:
    pages = _split_page_blocks(text)
    if pages:
        first_pages = [page_text for page_number, page_text in pages if page_number <= 2 and page_text]
        if first_pages:
            focused = "\n\n".join(first_pages)
            if len(focused) > max_chars:
                return _trim_text(focused, max_chars)
            return focused

    return _focus_section_text(text, "general_info", max_chars)


def _focus_section_text(text: str, section_key: str, max_chars: int) -> str:
    normalized_lines = text.splitlines()
    keywords = _section_keywords(section_key)
    if not normalized_lines or not keywords:
        return _trim_text(text, max_chars)

    matching_indexes: list[int] = []
    lowered_lines = [line.lower() for line in normalized_lines]
    for index, line in enumerate(lowered_lines):
        if any(keyword in line for keyword in keywords):
            matching_indexes.append(index)

    if not matching_indexes:
        return _trim_text(text, max_chars)

    window = 2
    selected_indexes: set[int] = set()
    for index in matching_indexes:
        for candidate in range(max(0, index - window), min(len(normalized_lines), index + window + 1)):
            selected_indexes.add(candidate)

    focused_lines = [normalized_lines[index] for index in sorted(selected_indexes)]
    focused_text = "\n".join(focused_lines).strip()
    if len(focused_text) > max_chars:
        return _trim_text(focused_text, max_chars)
    return focused_text


def _section_prompt_text(text: str, section_key: str, max_chars: int) -> str:
    if section_key == "general_info":
        focused = _general_info_text(text, max_chars)
    else:
        focused = _focus_section_text(text, section_key, max_chars)

    if not focused:
        return _trim_text(text, max_chars)
    return focused


def _section_user_prompt_with_text(
    syllabus: Syllabus,
    section_prompt: SectionPrompt,
    text: str,
) -> str:
    return f"""
Curso: {syllabus.course_code} - {syllabus.course_name}
Periodo académico: {syllabus.academic_period}
Carrera: {syllabus.career}
NRC: {syllabus.nrc}
Archivo: {syllabus.original_filename}

Instrucciones específicas del apartado:
{section_prompt.prompt}

Texto extraído del PDF:
<<<SYLLABUS_TEXT
{text}
SYLLABUS_TEXT>>>
""".strip()


def _extract_section_result(
    ai_client: JsonCompletionClient,
    syllabus: Syllabus,
    section_prompt: SectionPrompt,
    max_chars: int,
) -> dict[str, Any]:
    source_excerpt = _section_prompt_text(syllabus.text_content or "", section_prompt.key, max_chars)
    if not source_excerpt.strip():
        return {
            "section_name": section_prompt.name,
            "section_found": False,
            "confidence": 0.0,
            "relevant_excerpt": "",
            "extracted_variables": [],
            "missing_or_ambiguous_elements": ["No se encontró texto suficiente para esta sección."],
            "academic_interpretation": "Sección no detectada en el texto extraído.",
            "source_excerpt": "",
            "source_strategy": "missing",
        }
    prompt_text = _section_user_prompt_with_text(syllabus, section_prompt, source_excerpt)
    try:
        result = ai_client.complete_json(
            system_prompt=SECTION_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=prompt_text,
            schema_name=f"{section_prompt.key}_extraction",
            schema=SECTION_EXTRACTION_SCHEMA,
        )
    except AIProviderError:
        raise
    result["source_excerpt"] = source_excerpt
    result["source_strategy"] = "first_pages" if section_prompt.key == "general_info" else "keyword_window"
    return result


def _comparison_user_prompt(course_metadata: dict[str, Any], extracted_by_nrc: dict[str, Any]) -> str:
    return f"""
Curso analizado:
{json.dumps(course_metadata, ensure_ascii=False, indent=2)}

Información estructurada extraída por IA desde cada syllabus:
{json.dumps(extracted_by_nrc, ensure_ascii=False, indent=2)}

Compara los syllabus de este mismo curso y genera un reporte académico.
Debes cubrir, como mínimo:
- curso analizado;
- año-semestre;
- código y nombre del curso;
- NRC comparados;
- apartado analizado;
- variable afectada;
- diferencia detectada;
- NRC involucrados;
- nivel de gravedad;
- sugerencia de acción para el equipo académico.

Recuerda: si hay solo dos syllabus, no asumas cuál está correcto. Si hay tres o
más, identifica el patrón general solo cuando la evidencia lo permita.
""".strip()


def _comparison_user_prompt_from_sections(course_metadata: dict[str, Any], extracted_by_nrc: dict[str, Any]) -> str:
    comparison_input: list[dict[str, Any]] = []

    for nrc, syllabus_data in extracted_by_nrc.items():
        sections_payload: dict[str, Any] = {}
        for section_key, section_result in syllabus_data.get("sections", {}).items():
            sections_payload[section_key] = {
                "section_name": section_result.get("section_name", section_key),
                "source_excerpt": section_result.get("source_excerpt", ""),
                "source_strategy": section_result.get("source_strategy", ""),
                "extracted_variables": section_result.get("extracted_variables", []),
                "missing_or_ambiguous_elements": section_result.get("missing_or_ambiguous_elements", []),
                "academic_interpretation": section_result.get("academic_interpretation", ""),
            }

        comparison_input.append(
            {
                "nrc": nrc,
                "metadata": syllabus_data.get("metadata", {}),
                "sections": sections_payload,
            }
        )

    return f"""
Curso analizado:
{json.dumps(course_metadata, ensure_ascii=False, indent=2)}

Recortes relevantes por syllabus y por sección:
{json.dumps(comparison_input, ensure_ascii=False, indent=2)}

Compara los syllabus de este mismo curso usando únicamente los recortes de texto
y la información estructurada de cada sección. Devuelve un JSON con:
- análisis general del curso;
- NRC comparados;
- diferencias por apartado;
- gravedad de cada diferencia;
- sugerencia de acción para revisión académica.

Reglas obligatorias:
- No uses información que no aparezca en los recortes o en la extracción estructurada.
- Si una sección no está presente, indícalo como ausente y no inventes datos.
- Si hay solo dos syllabus, no asumas cuál está correcto.
- Si hay tres o más, identifica el patrón general solo cuando la evidencia lo permita.
""".strip()


def _comparison_user_prompt_for_section(
    course_metadata: dict[str, Any],
    section_key: str,
    section_name: str,
    extracted_by_nrc: dict[str, Any],
) -> str:
    section_specific_rules = ""
    if section_key == "evaluations":
        section_specific_rules = """
Reglas adicionales para evaluaciones:
- Antes de reportar una diferencia de ponderaciones, compara el conjunto de
  pares instrumento-porcentaje ignorando el orden textual.
- No reportes diferencia si ambos NRC contienen las mismas ponderaciones para
  los mismos instrumentos, aunque aparezcan en orden distinto. Por ejemplo,
  "30% Examen Final, 52.5% Pruebas" equivale a
  "52.5% Pruebas, 30% Examen Final".
- Reporta diferencia solo si cambia un porcentaje, falta un instrumento,
  aparece un instrumento adicional o cambia una condición académica.
""".strip()

    section_payload: list[dict[str, Any]] = []
    for nrc, syllabus_data in extracted_by_nrc.items():
        section = syllabus_data.get("sections", {}).get(section_key, {})
        section_payload.append(
            {
                "nrc": nrc,
                "metadata": syllabus_data.get("metadata", {}),
                "section_found": section.get("section_found", False),
                "source_strategy": section.get("source_strategy", ""),
                "source_excerpt": section.get("source_excerpt", ""),
                "structured_data": section.get("structured_data", {}),
                "missing_or_ambiguous_elements": section.get("missing_or_ambiguous_elements", []),
            }
        )

    return f"""
Curso analizado:
{json.dumps(course_metadata, ensure_ascii=False, indent=2)}

Apartado a comparar:
{section_name} ({section_key})

Texto del mismo apartado extraído localmente desde cada syllabus:
{json.dumps(section_payload, ensure_ascii=False, indent=2)}

Compara únicamente este apartado entre los NRC del mismo curso y devuelve un
JSON compatible con el esquema solicitado.

Reglas obligatorias:
- Usa solo los textos del apartado entregado; no inventes reglas ausentes.
- Distingue diferencias académicas reales de cambios de redacción equivalentes.
- Reporta como "Crítica" las diferencias que cambien evaluación, aprobación,
  eximición o nota final.
- Si el apartado falta en un NRC y aparece en otros, repórtalo como omisión.
- Si no hay diferencias relevantes, devuelve "inconsistencies": [].
- Si hay solo dos syllabus, no asumas cuál es correcto.
- Si hay tres o más, identifica patrón general solo cuando la evidencia lo permita.
{section_specific_rules}
""".strip()


def _estimate_payload_size(*parts: Any) -> int:
    return sum(len(json.dumps(part, ensure_ascii=False)) for part in parts)


def _canonical_variable_value(variable: dict[str, Any]) -> str:
    normalized = str(variable.get("normalized_value") or "").strip()
    if normalized:
        return normalized
    value = str(variable.get("value") or "").strip()
    return value


def _normalize_loose_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _canonical_percent(raw_percent: str) -> str:
    try:
        percent = Decimal(raw_percent.replace(",", "."))
    except InvalidOperation:
        return raw_percent.replace(",", ".").strip()
    return format(percent.normalize(), "f")


def _canonical_evaluation_label(raw_label: str) -> str:
    label = _normalize_loose_text(raw_label)
    label = re.sub(r"\b(ponderacion|porcentaje|peso|de|del|la|el|los|las)\b", " ", label)
    label = re.sub(r"\s+", " ", label).strip()
    if "examen" in label:
        return "examen final" if "final" in label else "examen"
    if "prueba" in label:
        return "pruebas"
    if "control" in label:
        return "controles"
    if "tarea" in label:
        return "tareas"
    if "laboratorio" in label or "lab" in label:
        return "laboratorio"
    if "proyecto" in label:
        return "proyecto"
    if "trabajo" in label:
        return "trabajos"
    if "quiz" in label or "cuestionario" in label:
        return "quiz"
    return label


def _extract_weight_pairs(text: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    chunks = re.split(r"[,;|\n]+", text)

    for chunk in chunks:
        cleaned = chunk.strip()
        if not cleaned:
            continue

        before_match = re.search(
            r"(?P<percent>\d+(?:[.,]\d+)?)\s*%\s*(?P<label>[^\d%,;|]+)",
            cleaned,
        )
        if before_match:
            label = _canonical_evaluation_label(before_match.group("label"))
            if label:
                pairs.add((_canonical_percent(before_match.group("percent")), label))
            continue

        after_match = re.search(
            r"(?P<label>[^\d%,;|]+?)\s*:?\s*(?P<percent>\d+(?:[.,]\d+)?)\s*%",
            cleaned,
        )
        if after_match:
            label = _canonical_evaluation_label(after_match.group("label"))
            if label:
                pairs.add((_canonical_percent(after_match.group("percent")), label))

    return pairs


def _split_values_by_nrc(text: str, involved_nrcs: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for nrc in involved_nrcs:
        pattern = rf"(?:NRC\s*)?{re.escape(str(nrc))}\s*:\s*(.*?)(?=\s+(?:NRC\s*)?\d+\s*:|$)"
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            values[str(nrc)] = match.group(1).strip()
    return values


def _is_equivalent_evaluation_weighting_alert(item: dict[str, Any]) -> bool:
    section = _normalize_loose_text(str(item.get("section") or ""))
    variable = _normalize_loose_text(str(item.get("variable") or ""))
    difference = str(item.get("difference") or "")
    evidence = str(item.get("evidence") or "")
    involved_nrcs = [str(nrc) for nrc in item.get("involved_nrcs", [])]

    if "evaluacion" not in section and "ponderacion" not in section:
        return False
    if "ponderacion" not in variable and "ponderacion" not in _normalize_loose_text(difference):
        return False
    if len(involved_nrcs) < 2:
        return False

    values_by_nrc = _split_values_by_nrc(f"{difference} {evidence}", involved_nrcs)
    if len(values_by_nrc) < 2:
        return False

    parsed_sets = [_extract_weight_pairs(value) for value in values_by_nrc.values()]
    if any(not parsed for parsed in parsed_sets):
        return False

    first = parsed_sets[0]
    return all(parsed == first for parsed in parsed_sets[1:])


def _canonical_rule_text(text: str) -> str:
    normalized = _normalize_loose_text(text)
    normalized = re.sub(r"\b(nota|calificacion)\s+(final|de aprobacion)\b", "nota final", normalized)
    normalized = re.sub(r"\bmayor\s+o\s+igual\s+(?:a\s+)?\b", ">= ", normalized)
    normalized = re.sub(r"\bigual\s+o\s+mayor\s+(?:a\s+)?\b", ">= ", normalized)
    normalized = re.sub(r"\bminima?\s+(?:de\s+)?\b", "minima ", normalized)
    normalized = re.sub(r"\b4 0\b", "4", normalized)
    normalized = re.sub(r"\b4 00\b", "4", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _is_same_rule_reported_as_difference(item: dict[str, Any]) -> bool:
    involved_nrcs = [str(nrc) for nrc in item.get("involved_nrcs", [])]
    if len(involved_nrcs) < 2:
        return False

    difference = str(item.get("difference") or "")
    evidence = str(item.get("evidence") or "")
    values_by_nrc = _split_values_by_nrc(difference, involved_nrcs)
    if len(values_by_nrc) < 2:
        values_by_nrc = _split_values_by_nrc(evidence, involved_nrcs)
    if len(values_by_nrc) < 2:
        return False

    canonical_values = {
        _canonical_rule_text(value)
        for value in values_by_nrc.values()
        if _canonical_rule_text(value)
    }
    return len(canonical_values) == 1


def _should_discard_ai_alert(item: dict[str, Any]) -> bool:
    return (
        _is_equivalent_evaluation_weighting_alert(item)
        or _is_same_rule_reported_as_difference(item)
    )


def _evaluation_weight_map(section_result: dict[str, Any]) -> dict[str, Decimal]:
    raw_weight_map = section_result.get("structured_data", {}).get("weight_map", {})
    weights: dict[str, Decimal] = {}
    if not isinstance(raw_weight_map, dict):
        return weights

    for instrument, raw_percent in raw_weight_map.items():
        try:
            weights[str(instrument)] = Decimal(str(raw_percent).replace(",", "."))
        except InvalidOperation:
            continue
    return weights


def _build_evaluation_table_comparison(
    extracted_by_nrc: dict[str, Any],
    compared_nrcs: list[str],
) -> dict[str, Any] | None:
    weights_by_nrc: dict[str, dict[str, Decimal]] = {}
    for nrc in compared_nrcs:
        section = extracted_by_nrc.get(nrc, {}).get("sections", {}).get("evaluations", {})
        weights = _evaluation_weight_map(section)
        if not weights:
            return None
        weights_by_nrc[nrc] = weights

    all_instruments = sorted(
        {
            instrument
            for weights in weights_by_nrc.values()
            for instrument in weights.keys()
        }
    )
    inconsistencies: list[dict[str, Any]] = []
    outlier_counts = {nrc: 0 for nrc in compared_nrcs}

    for instrument in all_instruments:
        values = {nrc: weights.get(instrument) for nrc, weights in weights_by_nrc.items()}
        present_values = {value for value in values.values() if value is not None}
        if len(present_values) == 1 and all(value is not None for value in values.values()):
            continue

        difference_parts = []
        for nrc in compared_nrcs:
            value = values[nrc]
            if value is None:
                difference_parts.append(f"NRC {nrc}: No informado")
            else:
                difference_parts.append(f"NRC {nrc}: {format_weight_map({instrument: value})}")
                outlier_counts[nrc] += 1

        variable = f"Ponderación de {instrument.title()}"
        inconsistencies.append(
            {
                "section": "Evaluaciones y Ponderaciones",
                "variable": variable,
                "difference": " | ".join(difference_parts),
                "involved_nrcs": compared_nrcs,
                "severity": "Crítica",
                "priority_rationale": "La ponderación de una evaluación cambia entre syllabus.",
                "suggestion": "Confirmar la ponderación oficial y actualizar los syllabus discrepantes.",
                "evidence": "Comparación determinística de tablas extraídas por coordenadas: "
                + " | ".join(
                    f"NRC {nrc}: {format_weight_map(weights)}"
                    for nrc, weights in weights_by_nrc.items()
                ),
                "is_main_alert": True,
            }
        )

    outlier_nrc = max(outlier_counts, key=outlier_counts.get) if outlier_counts else ""
    outlier_alert_count = outlier_counts.get(outlier_nrc, 0)
    return {
        "analysis_mode": "pairwise" if len(compared_nrcs) == 2 else "group_pattern",
        "compared_nrcs": compared_nrcs,
        "overall_summary": (
            "Se detectaron diferencias en ponderaciones de evaluaciones extraídas desde tablas."
            if inconsistencies
            else "No se detectaron diferencias en las ponderaciones tabulares de evaluaciones."
        ),
        "severity_counts": {"critica": len(inconsistencies), "moderada": 0, "menor": 0},
        "possible_outlier": {
            "nrc": outlier_nrc if outlier_alert_count else "",
            "alert_count": outlier_alert_count,
            "reason": "Presenta más diferencias en ponderaciones tabulares." if outlier_alert_count else "",
        },
        "inconsistencies": inconsistencies,
    }


def _variables_to_dict(section_result: dict[str, Any]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for variable in section_result.get("extracted_variables", []):
        name = str(variable.get("name") or "").strip()
        value = str(variable.get("value") or "").strip()
        if name:
            metadata[name] = value
    return metadata


def _build_local_comparison(course_metadata: dict[str, Any], extracted_by_nrc: dict[str, Any]) -> dict[str, Any]:
    nrcs = [str(nrc) for nrc in extracted_by_nrc.keys()]
    section_labels = {prompt.key: prompt.name for prompt in SECTION_PROMPTS}
    section_severities = {
        "evaluations": "Crítica",
        "approval_requirements": "Crítica",
        "exemption": "Crítica",
        "final_grade": "Crítica",
    }

    severity_counts = {"critica": 0, "moderada": 0, "menor": 0}
    inconsistencies: list[dict[str, Any]] = []
    alerts_by_nrc = {nrc: 0 for nrc in nrcs}

    for section_key in [prompt.key for prompt in SECTION_PROMPTS if prompt.key != "general_info"]:
        variables_by_name: dict[str, dict[str, str]] = {}
        for nrc, syllabus_data in extracted_by_nrc.items():
            section = syllabus_data.get("sections", {}).get(section_key, {})
            for variable in section.get("extracted_variables", []):
                variable_name = str(variable.get("name") or "Variable no especificada").strip()
                variables_by_name.setdefault(variable_name, {})[str(nrc)] = _canonical_variable_value(variable)

        for variable_name, values_by_nrc in variables_by_name.items():
            normalized_values = {value for value in values_by_nrc.values() if value}
            if len(normalized_values) <= 1:
                continue

            severity = section_severities.get(section_key, "Moderada")
            if section_key == "evaluations":
                severity = "Crítica" if any(any(ch.isdigit() for ch in value) for value in normalized_values) else "Moderada"

            difference_parts = []
            evidence_parts = []
            for nrc in nrcs:
                value = values_by_nrc.get(nrc, "No informado") or "No informado"
                difference_parts.append(f"NRC {nrc}: {value}")
                evidence_parts.append(f"{nrc}={value}")

            if severity == "Crítica":
                severity_counts["critica"] += 1
            elif severity == "Moderada":
                severity_counts["moderada"] += 1
            else:
                severity_counts["menor"] += 1

            for nrc in values_by_nrc.keys():
                alerts_by_nrc[nrc] = alerts_by_nrc.get(nrc, 0) + 1

            inconsistencies.append(
                {
                    "section": section_labels.get(section_key, section_key),
                    "variable": variable_name,
                    "difference": " | ".join(difference_parts),
                    "involved_nrcs": nrcs,
                    "severity": severity,
                    "priority_rationale": (
                        "Diferencia detectada en un apartado clave para evaluación, aprobación, eximición o nota final."
                        if severity == "Crítica"
                        else "Diferencia potencialmente relevante para la revisión académica."
                    ),
                    "suggestion": "Revisar y unificar la redacción oficial del syllabus para este apartado.",
                    "evidence": "; ".join(evidence_parts),
                    "is_main_alert": severity == "Crítica",
                }
            )

    if alerts_by_nrc:
        outlier_nrc = max(alerts_by_nrc, key=alerts_by_nrc.get)
        outlier_alerts = alerts_by_nrc[outlier_nrc]
        possible_outlier = {
            "nrc": outlier_nrc if outlier_alerts else "",
            "alert_count": outlier_alerts,
            "reason": "Acumula más diferencias estructurales respecto del resto." if outlier_alerts else "",
        }
    else:
        possible_outlier = {"nrc": "", "alert_count": 0, "reason": ""}

    return {
        "analysis_mode": "pairwise" if len(nrcs) == 2 else "group_pattern",
        "compared_nrcs": nrcs,
        "overall_summary": (
            f"Comparación local entre {len(nrcs)} syllabus basada en variables extraídas por sección."
            if inconsistencies
            else f"No se detectaron diferencias relevantes entre los {len(nrcs)} syllabus comparados."
        ),
        "severity_counts": severity_counts,
        "possible_outlier": possible_outlier,
        "inconsistencies": inconsistencies,
    }


def _build_comparison_payload(course_metadata: dict[str, Any], extracted_by_nrc: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"course_metadata": course_metadata, "syllabi": []}

    for nrc, syllabus_data in extracted_by_nrc.items():
        sections_payload: dict[str, Any] = {}
        for section_key, section_result in syllabus_data.get("sections", {}).items():
            sections_payload[section_key] = {
                "section_name": section_result.get("section_name", section_key),
                "source_excerpt": section_result.get("source_excerpt", ""),
                "source_strategy": section_result.get("source_strategy", ""),
                "structured_data": section_result.get("structured_data", {}),
                "extracted_variables": section_result.get("extracted_variables", []),
                "missing_or_ambiguous_elements": section_result.get("missing_or_ambiguous_elements", []),
                "academic_interpretation": section_result.get("academic_interpretation", ""),
            }

        payload["syllabi"].append(
            {
                "nrc": nrc,
                "metadata": syllabus_data.get("metadata", {}),
                "sections": sections_payload,
            }
        )

    return payload


def _normalize_comparison_output(
    comparison: dict[str, Any],
    extracted_by_nrc: dict[str, Any],
    ai_model: str,
) -> dict[str, Any]:
    raw_counts = comparison.get("severity_counts", {})
    possible_outlier = comparison.get("possible_outlier", {})
    normalized_outlier = None
    if possible_outlier.get("nrc"):
        normalized_outlier = {
            "nrc": possible_outlier.get("nrc", ""),
            "alerts": possible_outlier.get("alert_count", 0),
            "reason": possible_outlier.get("reason", ""),
        }

    inconsistencies = []
    for item in comparison.get("inconsistencies", []):
        inconsistencies.append(
            {
                "section": item.get("section", "Apartado no especificado"),
                "variable": item.get("variable", "Variable no especificada"),
                "difference": item.get("difference", ""),
                "involved_nrcs": [str(nrc) for nrc in item.get("involved_nrcs", [])],
                "severity": item.get("severity", "Moderada"),
                "suggestion": item.get("suggestion", ""),
                "evidence": {
                    "ai_evidence": item.get("evidence", ""),
                    "priority_rationale": item.get("priority_rationale", ""),
                    "is_main_alert": item.get("is_main_alert", True),
                },
            }
        )

    return {
        "compared_nrcs": [str(nrc) for nrc in comparison.get("compared_nrcs", [])],
        "inconsistencies": inconsistencies,
        "summary": {
            "compared_count": len(extracted_by_nrc),
            "severity_counts": {
                "Crítica": raw_counts.get("critica", 0),
                "Moderada": raw_counts.get("moderada", 0),
                "Menor": raw_counts.get("menor", 0),
            },
            "possible_outlier": normalized_outlier,
            "analysis_mode": comparison.get("analysis_mode", "pairwise"),
            "note": (
                "Con dos syllabus se reportan diferencias sin asumir cuál es correcto."
                if len(extracted_by_nrc) == 2
                else "Con tres o más syllabus la IA intenta identificar un patrón general cuando existe."
            ),
            "analysis_provider": "ollama",
            "ai_model": ai_model,
            "overall_summary": comparison.get("overall_summary", ""),
            "extracted_sections_by_nrc": extracted_by_nrc,
        },
    }


def _empty_section_comparison(
    section_key: str,
    section_name: str,
    compared_nrcs: list[str],
) -> dict[str, Any]:
    return {
        "analysis_mode": "pairwise" if len(compared_nrcs) == 2 else "group_pattern",
        "compared_nrcs": compared_nrcs,
        "overall_summary": f"No se encontró texto suficiente para comparar {section_name}.",
        "severity_counts": {"critica": 0, "moderada": 0, "menor": 0},
        "possible_outlier": {"nrc": "", "alert_count": 0, "reason": ""},
        "inconsistencies": [],
    }


def _combine_section_comparisons(
    comparisons: list[dict[str, Any]],
    compared_nrcs: list[str],
) -> dict[str, Any]:
    severity_counts = {"critica": 0, "moderada": 0, "menor": 0}
    inconsistencies: list[dict[str, Any]] = []
    outlier_counts = {nrc: 0 for nrc in compared_nrcs}
    summaries: list[str] = []

    for comparison in comparisons:
        summaries.append(str(comparison.get("overall_summary") or "").strip())
        for item in comparison.get("inconsistencies", []):
            if _should_discard_ai_alert(item):
                continue

            inconsistencies.append(item)
            severity = str(item.get("severity") or "").lower()
            if severity.startswith("cr"):
                severity_counts["critica"] += 1
            elif severity.startswith("men"):
                severity_counts["menor"] += 1
            else:
                severity_counts["moderada"] += 1

            for nrc in item.get("involved_nrcs", []):
                nrc_text = str(nrc)
                if nrc_text in outlier_counts:
                    outlier_counts[nrc_text] += 1

    if outlier_counts:
        outlier_nrc = max(outlier_counts, key=outlier_counts.get)
        alert_count = outlier_counts[outlier_nrc]
    else:
        outlier_nrc = ""
        alert_count = 0

    return {
        "analysis_mode": "pairwise" if len(compared_nrcs) == 2 else "group_pattern",
        "compared_nrcs": compared_nrcs,
        "overall_summary": (
            " ".join(summary for summary in summaries if summary)
            if inconsistencies
            else f"No se detectaron diferencias relevantes entre los {len(compared_nrcs)} syllabus comparados."
        ),
        "severity_counts": severity_counts,
        "possible_outlier": {
            "nrc": outlier_nrc if alert_count else "",
            "alert_count": alert_count,
            "reason": "Acumula más diferencias detectadas entre apartados." if alert_count else "",
        },
        "inconsistencies": inconsistencies,
    }


def analyze_syllabi_with_ai(
    syllabi: list[Syllabus],
    course_metadata: dict[str, Any],
    client: JsonCompletionClient | None = None,
    max_text_chars: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    ai_client = client or get_json_client()
    text_limit = max_text_chars or settings.ai_max_pdf_text_chars
    active_model = settings.local_model
    extracted_by_nrc: dict[str, Any] = {}

    for syllabus in syllabi:
        section_results = extract_sections_from_text(syllabus.text_content or "", text_limit)
        stored_path = str(getattr(syllabus, "stored_path", "") or "")
        evaluation_table = extract_evaluation_table_from_pdf(stored_path, text_limit)
        if evaluation_table is not None:
            section_results["evaluations"] = evaluation_table

        extracted_by_nrc[syllabus.nrc] = {
            "metadata": {
                "academic_period": syllabus.academic_period,
                "year": syllabus.year,
                "term": syllabus.term,
                "career": syllabus.career,
                "course_code": syllabus.course_code,
                "course_name": syllabus.course_name,
                "nrc": syllabus.nrc,
                "filename": syllabus.original_filename,
                "extraction_status": syllabus.extraction_status,
            },
            "sections": section_results,
        }

    compared_nrcs = [str(syllabus.nrc) for syllabus in syllabi]
    section_comparisons: list[dict[str, Any]] = []
    comparable_sections = [
        definition
        for definition in SECTION_DEFINITIONS
        if definition.key != "general_info"
    ]

    for definition in comparable_sections:
        if definition.key == "evaluations":
            table_comparison = _build_evaluation_table_comparison(extracted_by_nrc, compared_nrcs)
            if table_comparison is not None:
                section_comparisons.append(table_comparison)
                continue

        has_section_text = any(
            (syllabus_data.get("sections", {}).get(definition.key, {}).get("source_excerpt") or "").strip()
            for syllabus_data in extracted_by_nrc.values()
        )
        if not has_section_text:
            section_comparisons.append(
                _empty_section_comparison(definition.key, definition.name, compared_nrcs)
            )
            continue

        comparison = ai_client.complete_json(
            system_prompt=COMPARISON_SYSTEM_PROMPT,
            user_prompt=_comparison_user_prompt_for_section(
                course_metadata,
                definition.key,
                definition.name,
                extracted_by_nrc,
            ),
            schema_name=f"{definition.key}_comparison_report",
            schema=COMPARISON_SCHEMA,
        )
        section_comparisons.append(comparison)

    comparison = _combine_section_comparisons(section_comparisons, compared_nrcs)
    return _normalize_comparison_output(comparison, extracted_by_nrc, active_model)
