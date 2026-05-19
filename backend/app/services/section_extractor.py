from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SectionDefinition:
    key: str
    name: str
    headings: tuple[str, ...]


SECTION_DEFINITIONS: tuple[SectionDefinition, ...] = (
    SectionDefinition(
        key="general_info",
        name="Información General de la Asignatura",
        headings=(
            "Información de la Asignatura",
            "Información General de la Asignatura",
            "Datos Generales",
        ),
    ),
    SectionDefinition(
        key="evaluations",
        name="Evaluaciones y Ponderaciones",
        headings=(
            "Evaluaciones y Ponderaciones",
            "Sistema de Evaluación",
            "Evaluaciones",
        ),
    ),
    SectionDefinition(
        key="approval_requirements",
        name="Requisitos de Aprobación",
        headings=(
            "Requisitos de Aprobación",
            "Condiciones de Aprobación",
            "Requisitos para Aprobar",
        ),
    ),
    SectionDefinition(
        key="exemption",
        name="Criterios de Eximición",
        headings=(
            "Criterios de Eximición",
            "Eximición",
            "Eximición de Examen",
        ),
    ),
    SectionDefinition(
        key="final_grade",
        name="Nota Final de la Asignatura",
        headings=(
            "Nota Final de la Asignatura",
            "Cálculo de Nota Final",
            "Calificación Final",
        ),
    ),
)


BOUNDARY_HEADINGS: tuple[str, ...] = tuple(
    heading
    for definition in SECTION_DEFINITIONS
    for heading in definition.headings
) + (
    "Información del Instructor",
    "Descripción de la Asignatura",
    "Aporte al Perfil de Egreso",
    "Resultados de Aprendizaje",
    "Descripción de Contenidos por Unidad",
    "Metodologías de Enseñanza y Aprendizaje",
    "Estrategias de Enseñanza y Aprendizaje",
    "Cronograma de Actividades",
    "Recursos de Aprendizaje - Bibliografía Básica",
    "Bibliografía Básica",
    "Ausencia a Evaluaciones",
    "Justificación Ausencias a Evaluaciones",
)


def normalize_heading(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.fullmatch(r"--- Página \d+ ---", line):
            continue
        if re.fullmatch(r"Page \d+ of \d+", line, flags=re.IGNORECASE):
            continue
        lines.append(line)
    return lines


def _find_heading(lines: list[str], aliases: tuple[str, ...]) -> int | None:
    normalized_aliases = {normalize_heading(alias) for alias in aliases}
    for index, line in enumerate(lines):
        normalized_line = normalize_heading(line)
        if normalized_line in normalized_aliases:
            return index
    return None


def _boundary_indexes(lines: list[str]) -> list[int]:
    normalized_boundaries = {normalize_heading(heading) for heading in BOUNDARY_HEADINGS}
    indexes: list[int] = []
    for index, line in enumerate(lines):
        if normalize_heading(line) in normalized_boundaries:
            indexes.append(index)
    return indexes


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


def _keyword_excerpt(lines: list[str], keywords: tuple[str, ...], max_chars: int) -> str:
    normalized_keywords = [normalize_heading(keyword) for keyword in keywords]
    selected: set[int] = set()
    for index, line in enumerate(lines):
        normalized_line = normalize_heading(line)
        if any(keyword in normalized_line for keyword in normalized_keywords):
            for candidate in range(max(0, index - 4), min(len(lines), index + 5)):
                selected.add(candidate)

    excerpt = "\n".join(lines[index] for index in sorted(selected)).strip()
    return _trim_text(excerpt, max_chars)


def _placeholder(definition: SectionDefinition, reason: str) -> dict[str, Any]:
    return {
        "section_name": definition.name,
        "section_found": False,
        "confidence": 0.0,
        "relevant_excerpt": "",
        "extracted_variables": [],
        "missing_or_ambiguous_elements": [reason],
        "academic_interpretation": "Apartado no detectado con subtítulos conocidos.",
        "source_excerpt": "",
        "source_strategy": "missing",
    }


def extract_sections_from_text(text: str, max_chars: int) -> dict[str, dict[str, Any]]:
    lines = _clean_lines(text)
    if not lines:
        return {
            definition.key: _placeholder(definition, "No hay texto extraído del PDF.")
            for definition in SECTION_DEFINITIONS
        }

    boundary_indexes = _boundary_indexes(lines)
    sections: dict[str, dict[str, Any]] = {}

    for definition in SECTION_DEFINITIONS:
        start = _find_heading(lines, definition.headings)
        if start is None:
            if definition.key == "exemption":
                excerpt = _keyword_excerpt(
                    lines,
                    ("eximición", "eximirse", "eximido", "exoneración", "liberación de examen"),
                    max_chars,
                )
                if excerpt:
                    sections[definition.key] = {
                        "section_name": definition.name,
                        "section_found": True,
                        "confidence": 0.65,
                        "relevant_excerpt": excerpt,
                        "extracted_variables": [],
                        "missing_or_ambiguous_elements": [
                            "No se encontró subtítulo específico de eximición; se usó búsqueda por palabras clave."
                        ],
                        "academic_interpretation": "Recorte local obtenido por coincidencias de eximición.",
                        "source_excerpt": excerpt,
                        "source_strategy": "keyword_window",
                    }
                    continue

            sections[definition.key] = _placeholder(
                definition,
                "No se encontró el subtítulo de inicio para este apartado.",
            )
            continue

        next_boundaries = [index for index in boundary_indexes if index > start]
        end = min(next_boundaries) if next_boundaries else len(lines)
        excerpt = "\n".join(lines[start:end]).strip()
        excerpt = _trim_text(excerpt, max_chars)

        sections[definition.key] = {
            "section_name": definition.name,
            "section_found": bool(excerpt),
            "confidence": 1.0 if excerpt else 0.0,
            "relevant_excerpt": excerpt,
            "extracted_variables": [],
            "missing_or_ambiguous_elements": [],
            "academic_interpretation": "Apartado extraído localmente usando subtítulo inicial y siguiente subtítulo.",
            "source_excerpt": excerpt,
            "source_strategy": "heading_boundaries",
        }

    return sections
