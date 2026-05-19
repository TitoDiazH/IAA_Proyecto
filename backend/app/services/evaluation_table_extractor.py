from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - fallback for minimal local envs
    fitz = None

from app.services.section_extractor import BOUNDARY_HEADINGS, normalize_heading


EVALUATION_HEADINGS = (
    "Evaluaciones y Ponderaciones",
    "Sistema de Evaluación",
    "Evaluaciones",
)


@dataclass(frozen=True)
class PdfWord:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


@dataclass(frozen=True)
class VisualRow:
    page: int
    y0: float
    text: str
    words: tuple[PdfWord, ...]


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _decimal_from_percent(raw_value: str) -> Decimal | None:
    value = raw_value.replace(",", ".").strip()
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _canonical_percent(raw_value: str | Decimal) -> str:
    value = raw_value if isinstance(raw_value, Decimal) else _decimal_from_percent(raw_value)
    if value is None:
        return str(raw_value).strip()
    return format(value.normalize(), "f")


def _display_percent(value: Decimal) -> str:
    return f"{_canonical_percent(value)}%"


def _clean_label(raw_label: str) -> str:
    label = raw_label
    label = re.sub(r"\b\d+(?:[.,]\d+)?\b", " ", label)
    label = re.sub(r"\b(?:n|nro|numero|cantidad|fecha|semana|ponderacion|porcentaje|peso)\b", " ", label, flags=re.I)
    label = re.sub(r"\b(?:tipo|evaluacion|evaluaciones|actividad|instrumento)\b", " ", label, flags=re.I)
    label = re.sub(r"[%:;|,\-]+", " ", label)
    label = re.sub(r"\s+", " ", label).strip()
    return label


def _canonical_instrument(raw_label: str) -> str:
    label = _normalize_text(_clean_label(raw_label))
    label = re.sub(r"\b(de|del|la|el|los|las|y)\b", " ", label)
    label = re.sub(r"\s+", " ", label).strip()

    if "examen" in label:
        return "examen final" if "final" in label else "examen"
    if "prueba" in label or re.search(r"\bpep\b", label):
        return "pruebas"
    if "control" in label:
        return "controles"
    if "tarea" in label:
        return "tareas"
    if "laboratorio" in label or re.search(r"\blab\b", label):
        return "laboratorio"
    if "proyecto" in label:
        return "proyecto"
    if "trabajo" in label:
        return "trabajos"
    if "quiz" in label or "cuestionario" in label:
        return "quiz"
    if "participacion" in label:
        return "participacion"
    return label


def _instrument_display_name(canonical: str) -> str:
    names = {
        "examen final": "Examen Final",
        "examen": "Examen",
        "pruebas": "Pruebas",
        "controles": "Controles",
        "tareas": "Tareas",
        "laboratorio": "Laboratorio",
        "proyecto": "Proyecto",
        "trabajos": "Trabajos",
        "quiz": "Quiz",
        "participacion": "Participación",
    }
    return names.get(canonical, canonical.title())


def _group_words_into_rows(words: list[PdfWord], y_tolerance: float = 3.0) -> list[VisualRow]:
    grouped: list[list[PdfWord]] = []
    baselines: list[float] = []

    for word in sorted(words, key=lambda item: (item.page, item.y0, item.x0)):
        target_index: int | None = None
        for index, baseline in enumerate(baselines):
            same_page = grouped[index] and grouped[index][0].page == word.page
            if same_page and abs(word.y0 - baseline) <= y_tolerance:
                target_index = index
                break

        if target_index is None:
            grouped.append([word])
            baselines.append(word.y0)
            continue

        grouped[target_index].append(word)
        baselines[target_index] = (
            baselines[target_index] * (len(grouped[target_index]) - 1) + word.y0
        ) / len(grouped[target_index])

    rows: list[VisualRow] = []
    for row_words in grouped:
        sorted_words = tuple(sorted(row_words, key=lambda item: item.x0))
        rows.append(
            VisualRow(
                page=sorted_words[0].page,
                y0=sum(word.y0 for word in sorted_words) / len(sorted_words),
                text=" ".join(word.text for word in sorted_words),
                words=sorted_words,
            )
        )
    return sorted(rows, key=lambda item: (item.page, item.y0))


def _find_evaluation_bounds(rows: list[VisualRow]) -> tuple[int, int] | None:
    evaluation_aliases = {normalize_heading(heading) for heading in EVALUATION_HEADINGS}
    boundary_aliases = {normalize_heading(heading) for heading in BOUNDARY_HEADINGS}
    start: int | None = None

    for index, row in enumerate(rows):
        normalized = normalize_heading(row.text)
        if normalized in evaluation_aliases:
            start = index
            break

    if start is None:
        return None

    end = len(rows)
    for index in range(start + 1, len(rows)):
        normalized = normalize_heading(rows[index].text)
        if normalized in boundary_aliases and normalized not in evaluation_aliases:
            end = index
            break

    return start, end


def _label_for_percent(row_text: str, match: re.Match[str]) -> str:
    before = row_text[: match.start()].strip(" :;|,-")
    after = row_text[match.end() :].strip(" :;|,-")

    if before:
        label = before
        previous_percent = list(re.finditer(r"\d+(?:[.,]\d+)?\s*%", before))
        if previous_percent:
            label = before[previous_percent[-1].end() :].strip(" :;|,-")
        return label
    return after


def parse_evaluation_items_from_rows(rows: list[VisualRow]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for row in rows:
        normalized = _normalize_text(row.text)
        if not normalized or "ponderacion" in normalized and "%" not in row.text:
            continue

        for match in re.finditer(r"(?P<percent>\d+(?:[.,]\d+)?)\s*%", row.text):
            percent = _decimal_from_percent(match.group("percent"))
            if percent is None:
                continue

            raw_label = _label_for_percent(row.text, match)
            canonical = _canonical_instrument(raw_label)
            if not canonical:
                continue

            items.append(
                {
                    "instrument": _instrument_display_name(canonical),
                    "normalized_instrument": canonical,
                    "weight": float(percent),
                    "weight_percent": _canonical_percent(percent),
                    "raw_label": _clean_label(raw_label),
                    "raw_row": row.text,
                    "page": row.page,
                    "y0": round(row.y0, 2),
                }
            )

    return items


def weight_map_from_items(items: list[dict[str, Any]]) -> dict[str, Decimal]:
    weights: dict[str, Decimal] = {}
    for item in items:
        instrument = str(item.get("normalized_instrument") or "").strip()
        if not instrument:
            continue
        percent = _decimal_from_percent(str(item.get("weight_percent") or item.get("weight") or ""))
        if percent is None:
            continue
        weights[instrument] = weights.get(instrument, Decimal("0")) + percent
    return weights


def format_weight_map(weights: dict[str, Decimal]) -> str:
    return ", ".join(
        f"{_instrument_display_name(instrument)}: {_display_percent(percent)}"
        for instrument, percent in sorted(weights.items())
    )


def extract_evaluation_table_from_pdf(path: str | Path, max_chars: int) -> dict[str, Any] | None:
    if fitz is None:
        return None

    pdf_path = Path(path)
    if not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
        return None

    words: list[PdfWord] = []
    try:
        document = fitz.open(str(pdf_path))
    except Exception:
        return None

    try:
        for page_index, page in enumerate(document, start=1):
            for raw_word in page.get_text("words", sort=True):
                x0, y0, x1, y1, text = raw_word[:5]
                words.append(PdfWord(page_index, x0, y0, x1, y1, text))
    except Exception:
        return None
    finally:
        document.close()

    rows = _group_words_into_rows(words)
    bounds = _find_evaluation_bounds(rows)
    if bounds is None:
        return None

    start, end = bounds
    section_rows = rows[start:end]
    excerpt = "\n".join(row.text for row in section_rows).strip()
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip()

    items = parse_evaluation_items_from_rows(section_rows)
    if not items:
        return None

    weights = weight_map_from_items(items)
    return {
        "section_name": "Evaluaciones y Ponderaciones",
        "section_found": True,
        "confidence": 0.9,
        "relevant_excerpt": excerpt,
        "extracted_variables": [
            {
                "name": item["instrument"],
                "value": f"{item['weight_percent']}%",
                "normalized_value": item["weight_percent"],
                "evidence": item["raw_row"],
                "academic_relevance": "Ponderación de evaluación extraída desde tabla por coordenadas.",
            }
            for item in items
        ],
        "missing_or_ambiguous_elements": [],
        "academic_interpretation": "Tabla de evaluaciones reconstruida localmente usando coordenadas del PDF.",
        "source_excerpt": excerpt,
        "source_strategy": "pdf_words_table",
        "structured_data": {
            "evaluation_items": items,
            "weight_map": {
                instrument: _canonical_percent(percent)
                for instrument, percent in sorted(weights.items())
            },
        },
    }
