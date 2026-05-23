from __future__ import annotations

import csv
from io import StringIO
from re import IGNORECASE, findall, search, split, sub
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile
from io import BytesIO
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session, selectinload

from app.models import AnalysisReport, CourseGroup
from app.services.filename_parser import normalize_course_name


HEADER_ROWS = [
    ["", "", "", "NOTA PRESENTACIÓN (NP)", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "Controles y/o Tareas", "", "Pruebas", "", "Laboratorio (NL)", "", "Taller HT", "Otro", "", "Examen (NE)", "", "", "", "", "", ""],
    [
        "Curso",
        "Codigo",
        "NRC",
        "Pond",
        "Cant",
        "Pond",
        "Cant",
        "Pond",
        "Cant",
        "Pond",
        "Pond",
        "Desc",
        "Pond",
        "Cant",
        "Requisitos Aprobación",
        "Requisitos Exención",
        "NOTA FINAL",
        "NOTA FINAL REPROBADOS",
        "Otros Criterios",
    ],
]

COLUMNS = HEADER_ROWS[-1]


def build_conditions_export_table(db: Session) -> dict[str, Any]:
    groups = (
        db.query(CourseGroup)
        .options(
            selectinload(CourseGroup.syllabi),
            selectinload(CourseGroup.reports).selectinload(AnalysisReport.inconsistencies),
        )
        .order_by(CourseGroup.academic_period.desc(), CourseGroup.course_code.asc())
        .all()
    )

    rows: list[list[str]] = []
    for group in groups:
        latest = _latest_report(group)
        if latest is None or latest.status != "completed":
            continue

        normalized_by_nrc = _normalized_by_nrc_for_report(latest)

        for syllabus in sorted(group.syllabi, key=lambda item: item.nrc):
            normalized = normalized_by_nrc.get(str(syllabus.nrc), {})
            rows.append(_build_row(group, syllabus.nrc, normalized))

    return {
        "header_rows": HEADER_ROWS,
        "columns": COLUMNS,
        "rows": rows,
        "row_count": len(rows),
    }


def conditions_table_to_csv(table: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerows(table["header_rows"])
    writer.writerows(table["rows"])
    return output.getvalue()


def conditions_table_to_xlsx(table: dict[str, Any]) -> bytes:
    rows = [*table["header_rows"], *table["rows"]]
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_relationships_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships_xml())
        archive.writestr("xl/worksheets/sheet1.xml", _worksheet_xml(rows))
    return buffer.getvalue()


def _latest_report(group: CourseGroup) -> AnalysisReport | None:
    if not group.reports:
        return None
    return max(group.reports, key=lambda report: report.created_at)


def _normalized_by_nrc_for_report(report: AnalysisReport) -> dict[str, Any]:
    summary = report.summary if isinstance(report.summary, dict) else {}
    normalized_by_nrc = summary.get("normalized_syllabi_by_nrc", {})
    if isinstance(normalized_by_nrc, dict) and normalized_by_nrc:
        return normalized_by_nrc
    return {}


def _build_row(group: CourseGroup, nrc: str, normalized: Any) -> list[str]:
    normalized = normalized if isinstance(normalized, dict) else {}
    evaluations = normalized.get("evaluaciones") if isinstance(normalized.get("evaluaciones"), list) else []
    categories = _categorize_evaluations(evaluations)
    export_fields = normalized.get("conditions_export") if isinstance(normalized.get("conditions_export"), dict) else {}
    requirements = _clean(export_fields.get("requisitos_aprobacion")) or _summarize_requirements(
        normalized.get("requisitos_aprobacion")
    )
    exemption = _clean(
        export_fields.get("requisitos_exencion") or export_fields.get("requisitos_eximicion")
    ) or _summarize_exemption_from_sections(
        normalized.get("requisitos_aprobacion"),
        normalized.get("nota_final"),
    )
    final_grade = _clean(normalized.get("nota_final"))
    final_formula = _clean(export_fields.get("formula_nota_final") or export_fields.get("nota_final"))
    failed_rules = _clean(export_fields.get("nota_final_reprobados") or export_fields.get("nota_final_reprobacion"))
    other_criteria = _clean(export_fields.get("otros_criterios"))
    # Normalizar comas decimales en fórmulas (p. ej. '0,7' -> '0.7')
    final_formula = _normalize_formula_decimals(final_formula)
    failed_rules = _normalize_formula_decimals(failed_rules)
    other_criteria = _normalize_formula_decimals(other_criteria)
    if _is_placeholder_formula(final_formula):
        final_formula = ""
    if not final_formula and not failed_rules and not other_criteria:
        final_formula, failed_rules, other_criteria = _split_final_grade(final_grade)
    if _is_placeholder_formula(final_formula):
        final_formula = ""
    if not final_formula:
        final_formula = "No especificado"

    return [
        normalize_course_name(group.course_name),
        _clean(group.course_code),
        _clean(nrc),
        categories["controles"]["weight"],
        categories["controles"]["count"],
        categories["pruebas"]["weight"],
        categories["pruebas"]["count"],
        categories["laboratorio"]["weight"],
        categories["laboratorio"]["count"],
        categories["taller"]["weight"],
        categories["otro"]["weight"],
        categories["otro"]["description"],
        categories["examen"]["weight"],
        categories["examen"]["count"],
        requirements,
        exemption or "-",
        final_formula,
        failed_rules,
        other_criteria,
    ]


def _categorize_evaluations(evaluations: list[Any]) -> dict[str, dict[str, str]]:
    categories = {
        "controles": [],
        "pruebas": [],
        "laboratorio": [],
        "taller": [],
        "otro": [],
        "examen": [],
    }

    for item in evaluations:
        if not isinstance(item, dict):
            continue
        category = _evaluation_category(item)
        categories[category].append(item)

    return {
        key: {
            "weight": _format_weight(sum(_weight(item.get("ponderacion")) for item in items)),
            "count": _format_count(items),
            "description": "; ".join(_clean(item.get("descripcion")) for item in items if _clean(item.get("descripcion"))),
        }
        for key, items in categories.items()
    }


def _evaluation_category(item: dict[str, Any]) -> str:
    text = f"{item.get('tipo') or ''} {item.get('descripcion') or ''}".lower()
    if any(token in text for token in ["examen", "ne"]):
        return "examen"
    if any(token in text for token in ["laboratorio", "laborator", "nl"]):
        return "laboratorio"
    if "taller" in text:
        return "taller"
    if any(token in text for token in ["prueba", "catedra", "cátedra", "np"]):
        return "pruebas"
    if any(token in text for token in ["control", "tarea"]):
        return "controles"
    return "otro"


def _weight(value: Any) -> float:
    if value is None:
        return 0
    try:
        return float(str(value).replace("%", "").replace(",", ".").strip())
    except ValueError:
        return 0


def _format_weight(value: float) -> str:
    if value <= 0:
        return ""
    if value.is_integer():
        return f"{int(value)}%"
    return f"{value:.1f}%"


def _format_count(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    for item in items:
        text = f"{item.get('tipo') or ''} {item.get('descripcion') or ''}"
        match = search(r"\b(\d{1,2})\s+(?:pruebas?|controles?|tareas?|laboratorios?|talleres?|ex[aá]menes?)\b", text, flags=IGNORECASE)
        if match:
            return match.group(1)
    return str(len(items))


def _split_final_grade(text: str) -> tuple[str, str, str]:
    if not text:
        return "", "", ""

    parts = _split_sentences_preserving_decimals(text)
    formulas = _extract_nf_formulas(text)
    failed_parts = [
        _compact_condition(part)
        for part in parts
        if _looks_like_failed_final_grade_rule(part)
    ]
    failed_parts = [part for part in failed_parts if part]
    other_parts = [
        part
        for part in parts
        if part not in failed_parts
        and "promedio final" not in part.lower()
        and "calcula de la siguiente forma" not in part.lower()
        and not (part.lower().startswith("si ") and "nf" in part.lower())
    ]

    # If we found an explicit NF formula, use it. Otherwise avoid returning
    # the full paragraph as the formula (that causes long text to appear in the
    # "NOTA FINAL" column). Keep the original text in `other_parts` so it is
    # still available in "Otros Criterios" when needed.
    formula = formulas[0] if formulas else ""
    if not formula and text and text not in other_parts:
        other_parts.insert(0, text)

    return formula, "; ".join(failed_parts), "; ".join(other_parts)


def _normalize_formula_decimals(text: str) -> str:
    """Convertir comas decimales tipo '0,7' a '0.7' dentro de fórmulas/fragmentos.

    Solo reemplaza comas que estén entre dígitos para evitar tocar texto normal.
    """
    if not text:
        return text
    return sub_decimal_commas(text)


def _extract_nf_formulas(text: str) -> list[str]:
    formulas = []
    for match in _split_sentences_preserving_decimals(text):
        formula = _formula_from_explicit_match(match)
        if formula and formula not in formulas:
            formulas.append(formula)
    weighted = [
        formula
        for formula in formulas
        if any(token in formula.upper() for token in ["NP", "NE", "EX", "NCAT", "NL"])
        and any(token in formula for token in ["+", "*", "0."])
    ]
    return weighted or formulas


def _formula_from_explicit_match(text: str) -> str:
    clean = _clean(text.strip(" .;:"))
    if not clean:
        return ""
    if search(r"(?:\bNF\s*=|nota\s+final\s*=)", clean, flags=IGNORECASE):
        formula = _extract_nf_assignment(clean) or clean
        return "" if _is_placeholder_formula(formula) else formula
    explicit_formula = _formula_from_explicit_weighted_text(clean)
    if explicit_formula:
        return explicit_formula
    if _looks_like_weighted_expression(clean):
        return f"NF = {clean}"
    return ""


def _extract_nf_assignment(text: str) -> str:
    match = search(r"\bNF\s*=", text, flags=IGNORECASE)
    if not match:
        return ""
    return text[match.start():].strip(" .;:")


def _formula_from_explicit_weighted_text(text: str) -> str:
    pairs = search_all_weight_component_pairs(text)
    if len(pairs) < 2:
        return ""

    components = []
    for percent, label in pairs:
        try:
            weight = float(percent.replace(",", ".")) / 100
        except ValueError:
            return ""
        if weight <= 0 or weight > 1:
            return ""
        components.append(f"{weight:g}*{label.upper()}")
    return f"NF = {' + '.join(components)}"


def search_all_weight_component_pairs(text: str) -> list[tuple[str, str]]:
    pairs = findall(
        r"(\d{1,3}(?:[.,]\d+)?)\s*%\s*(?:de\s+)?([A-Z]{1,6})\b",
        text,
        flags=IGNORECASE,
    )
    if len(pairs) >= 2:
        return pairs
    return findall(
        r"(\d+(?:[.,]\d+)?)\s*(?:por\s+ciento|%)\s*(?:de\s+)?(?:la\s+)?(?:nota\s+)?([A-Z]{1,6})\b",
        text,
        flags=IGNORECASE,
    )


def _looks_like_weighted_expression(text: str) -> bool:
    upper = text.upper()
    has_component = len(set(findall(r"\b(?:NP|NE|EX|NCAT|NL|P\d*|C\d*|T\d*)\b", upper))) >= 2
    has_weight = bool(search(r"\b0\.\d+\s*\*?\s*[A-Z]", upper) or search(r"\b\d{1,3}\s*%\s*(?:DE\s+)?[A-Z]", upper))
    has_operator = any(operator in text for operator in ["+", "*"])
    return has_component and has_weight and has_operator


def _looks_like_failed_final_grade_rule(text: str) -> bool:
    lowered = text.lower()
    failure_markers = ["reprob", "<", "menor", "inferior", "no cumple", "caso contrario", "en caso contrario"]
    return any(marker in lowered for marker in failure_markers) and (
        "nf" in lowered or "nota final" in lowered or "reprueba" in lowered
    )


def _split_sentences_preserving_decimals(text: str) -> list[str]:
    if not text:
        return []
    parts = split(r"\s*(?:[•\n]+|(?<!\d)\.(?!\d))\s*", text)
    return [part.strip(" .;") for part in parts if part.strip(" .;")]


def sub_decimal_commas(text: str) -> str:
    return sub(r"(?<=\d),(?=\d)", ".", text)


def _compact_condition(text: str) -> str:
    clean = _clean(text.strip(" .;"))
    if not clean:
        return ""
    if ":" in clean:
        condition, consequence = clean.split(":", 1)
        return f"{condition.strip()} -> {consequence.strip()}"
    return clean


def _summarize_requirements(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""

    requirements = []
    patterns = [
        (r"NP\s*(?:>=|≥|mayor\s+o\s+igual\s+a?)\s*(\d+(?:[.,]\d+)?)", "NP"),
        (r"NE\s*(?:>=|≥|mayor\s+o\s+igual\s+a?)\s*(\d+(?:[.,]\d+)?)", "NE"),
        (r"NF\s*(?:>=|≥|mayor\s+o\s+igual\s+a?)\s*(\d+(?:[.,]\d+)?)", "NF"),
        (r"nota\s+de\s+presentaci[oó]n\s+.*?(?:>=|≥|mayor\s+o\s+igual\s+a?)\s*(\d+(?:[.,]\d+)?)", "NP"),
        (r"examen\s+.*?(?:>=|≥|mayor\s+o\s+igual\s+a?)\s*(\d+(?:[.,]\d+)?)", "NE"),
        (r"nota\s+final\s+.*?(?:>=|≥|mayor\s+o\s+igual\s+a?)\s*(\d+(?:[.,]\d+)?)", "NF"),
    ]
    for pattern, label in patterns:
        match = search(pattern, text, flags=IGNORECASE)
        if match:
            requirement = f"{label}>={_normalize_number(match.group(1))}"
            if requirement not in requirements:
                requirements.append(requirement)

    return "; ".join(requirements) or text


def _summarize_exemption(value: Any) -> str:
    text = _clean(value)
    if not text or text == "-":
        return "-"

    patterns = [
        r"NP\s*(?:>=|≥|mayor\s+o\s+igual\s+a?)\s*(\d+(?:[.,]\d+)?)",
        r"nota\s+de\s+presentaci[oó]n\s+.*?(?:>=|≥|mayor\s+o\s+igual\s+a?)\s*(\d+(?:[.,]\d+)?)",
        r"promedio\s+.*?(?:>=|≥|mayor\s+o\s+igual\s+a?)\s*(\d+(?:[.,]\d+)?)",
    ]
    for pattern in patterns:
        match = search(pattern, text, flags=IGNORECASE)
        if match:
            return f"NP>={_normalize_number(match.group(1))}"
    return text


def _summarize_exemption_from_sections(*values: Any) -> str:
    for value in values:
        text = _clean(value)
        if not text or "exim" not in text.lower():
            continue
        summary = _summarize_exemption(text)
        if summary and summary != "-":
            return summary
    return ""


def _is_placeholder_formula(value: str) -> bool:
    if not value:
        return False
    compact = sub(r"\s+", "", value).upper()
    return compact in {"NF=0", "NOTAFINAL=0"}


def _normalize_number(value: str) -> str:
    return value.replace(",", ".")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _cell_ref(row_index: int, col_index: int) -> str:
    letters = ""
    col = col_index
    while col:
        col, remainder = divmod(col - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row_index}"


def _worksheet_xml(rows: list[list[str]]) -> str:
    row_xml = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            ref = _cell_ref(row_index, col_index)
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{''.join(row_xml)}</sheetData>
</worksheet>'''


def _content_types_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>'''


def _root_relationships_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''


def _workbook_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Condiciones" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''


def _workbook_relationships_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>'''
