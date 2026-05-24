from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any


def normalize_for_citation_match(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()
    text = re.sub(r"[^a-z0-9%.,+=-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _as_page(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _source_key(nrc: str, section: str, field_path: str) -> str:
    safe_section = re.sub(r"[^a-z0-9_]+", "_", section.lower()).strip("_")
    safe_field = re.sub(r"[^a-z0-9_.\\[\\]-]+", "_", field_path.lower()).strip("_")
    return f"{nrc}:{safe_section}:{safe_field}"


def build_source_entry(
    *,
    nrc: str,
    section: str,
    field_path: str,
    text: Any,
    page_numbers: list[int] | None = None,
    source_type: str = "text",
) -> dict[str, Any] | None:
    normalized_text = str(text or "").strip()
    if not nrc or not normalized_text:
        return None

    pages = [
        page
        for page in (page_numbers or [])
        if isinstance(page, int) and page > 0
    ]
    return {
        "source_id": _source_key(nrc, section, field_path),
        "nrc": nrc,
        "section": section,
        "field_path": field_path,
        "page": pages[0] if pages else None,
        "page_numbers": pages,
        "text": normalized_text,
        "source_type": source_type,
    }


def build_source_index(normalized_syllabi_by_nrc: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    sources_by_nrc: dict[str, list[dict[str, Any]]] = {}

    for nrc, syllabus in normalized_syllabi_by_nrc.items():
        if not isinstance(syllabus, dict):
            continue

        nrc_text = str(syllabus.get("nrc") or nrc or "").strip()
        if not nrc_text:
            continue

        sources: list[dict[str, Any]] = []
        raw_sources = syllabus.get("_sources") if isinstance(syllabus.get("_sources"), list) else []
        for raw_source in raw_sources:
            if not isinstance(raw_source, dict):
                continue
            text = str(raw_source.get("text") or "").strip()
            if not text:
                continue
            source_id = str(raw_source.get("source_id") or "").strip()
            sources.append(
                {
                    "source_id": source_id or _source_key(
                        nrc_text,
                        str(raw_source.get("section") or "syllabus"),
                        str(raw_source.get("field_path") or len(sources)),
                    ),
                    "nrc": nrc_text,
                    "section": str(raw_source.get("section") or "").strip() or None,
                    "field_path": str(raw_source.get("field_path") or "").strip() or None,
                    "page": _as_page(raw_source.get("page")),
                    "page_numbers": [
                        page
                        for page in (_as_page(item) for item in raw_source.get("page_numbers", []))
                        if page is not None
                    ],
                    "text": text,
                    "source_type": str(raw_source.get("source_type") or "text"),
                }
            )

        if not sources:
            for section in ("requisitos_aprobacion", "nota_final"):
                entry = build_source_entry(
                    nrc=nrc_text,
                    section=section,
                    field_path=section,
                    text=syllabus.get(section),
                )
                if entry:
                    sources.append(entry)
            for index, evaluation in enumerate(syllabus.get("evaluaciones", []) or []):
                if not isinstance(evaluation, dict):
                    continue
                text = _format_evaluation_source_text(evaluation)
                entry = build_source_entry(
                    nrc=nrc_text,
                    section="evaluaciones",
                    field_path=f"evaluaciones[{index}]",
                    text=text,
                    source_type="evaluation_row",
                )
                if entry:
                    sources.append(entry)

        sources_by_nrc[nrc_text] = sources

    return sources_by_nrc


def resolve_evidence_item(
    item: dict[str, Any],
    sources_by_nrc: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    nrc = str(item.get("nrc") or "").strip()
    if not nrc:
        return None

    text = str(item.get("text") or item.get("quote") or item.get("citation") or "").strip()
    source_id = str(item.get("source_id") or item.get("source_ref") or item.get("evidence_ref") or "").strip()
    requested_page = _as_page(item.get("page"))
    sources = sources_by_nrc.get(nrc, [])
    source = _find_source(source_id, text, sources)

    if source is not None:
        source_text = source["text"]
        resolved_text = source_text if source_id else (text or source_text)
        match_status = "verified"
        confidence = _source_match_confidence(text or source_text, source_text)
        if confidence < 0.98:
            match_status = "approximate" if confidence >= 0.62 else "source_resolved"

        return {
            "nrc": nrc,
            "page": requested_page or source.get("page"),
            "text": resolved_text,
            "source_id": source["source_id"],
            "section": source.get("section"),
            "field_path": source.get("field_path"),
            "match_status": match_status,
            "confidence": round(confidence, 3),
            "rects": [],
        }

    if not text:
        return None

    return {
        "nrc": nrc,
        "page": requested_page,
        "text": text,
        "source_id": source_id or None,
        "section": None,
        "field_path": None,
        "match_status": "unverified",
        "confidence": 0,
        "rects": [],
    }


def _find_source(source_id: str, text: str, sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    if source_id:
        for source in sources:
            if source.get("source_id") == source_id:
                return source

    normalized_text = normalize_for_citation_match(text)
    if not normalized_text:
        return None

    best_source = None
    best_score = 0.0
    for source in sources:
        source_text = normalize_for_citation_match(source.get("text"))
        if not source_text:
            continue
        if normalized_text in source_text or source_text in normalized_text:
            score = min(len(normalized_text), len(source_text)) / max(len(normalized_text), len(source_text))
            score = max(score, 0.92)
        else:
            score = _similarity(normalized_text, source_text)
        if score > best_score:
            best_score = score
            best_source = source

    return best_source if best_score >= 0.62 else None


def _similarity(left: str, right: str) -> float:
    normalized_left = normalize_for_citation_match(left)
    normalized_right = normalize_for_citation_match(right)
    if not normalized_left or not normalized_right:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _source_match_confidence(citation_text: str, source_text: str) -> float:
    normalized_citation = normalize_for_citation_match(citation_text)
    normalized_source = normalize_for_citation_match(source_text)
    if not normalized_citation or not normalized_source:
        return 0.0
    if normalized_citation == normalized_source:
        return 1.0
    if normalized_citation in normalized_source or normalized_source in normalized_citation:
        return 0.99
    return _similarity(normalized_citation, normalized_source)


def _format_evaluation_source_text(evaluation: dict[str, Any]) -> str:
    tipo = str(evaluation.get("tipo") or evaluation.get("type") or "").strip()
    ponderacion = evaluation.get("ponderacion", evaluation.get("weight_total"))
    descripcion = str(evaluation.get("descripcion") or evaluation.get("description") or "").strip()

    parts = []
    if tipo:
        parts.append(tipo)
    if ponderacion is not None:
        parts.append(f"{ponderacion}%")
    if descripcion:
        parts.append(descripcion)
    return " ".join(parts).strip()
