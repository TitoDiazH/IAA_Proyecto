from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SyllabusSectionSpec:
    key: str
    name: str


SYLLABUS_SECTIONS: tuple[SyllabusSectionSpec, ...] = (
    SyllabusSectionSpec("evaluaciones_y_ponderaciones", "Evaluaciones y Ponderaciones"),
    SyllabusSectionSpec("requisitos_aprobacion", "Requisitos de Aprobación"),
    SyllabusSectionSpec("criterios_eximicion", "Criterios de Eximición"),
    SyllabusSectionSpec("nota_final", "Nota Final de la Asignatura"),
)

SYLLABUS_EXTRACTION_SYSTEM_PROMPT = """
Eres un especialista en revisión académica de syllabus universitarios.
Tu tarea es leer un syllabus por páginas y devolver exclusivamente un JSON válido,
normalizado y trazable.

Reglas obligatorias:
- No inventes información.
- Si un dato no aparece explícitamente, usa null.
- Si un apartado no existe, marca found como false, page_numbers como lista vacía,
  raw_evidence como null y structured_data como null.
- Conserva la trazabilidad usando page_numbers y raw_evidence.
- Usa únicamente la evidencia textual suministrada.
- Si hay ambigüedad, conserva null y agrega una advertencia en warnings.
- Todo el contenido textual que produzcas en el JSON debe estar en español neutro.
- No devuelvas markdown, explicación ni texto adicional.
""".strip()


def _evaluation_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "type": {"type": ["string", "null"]},
            "quantity": {"type": ["number", "null"]},
            "weight_total": {"type": ["number", "null"]},
            "weight_each": {"type": ["number", "null"]},
            "description": {"type": ["string", "null"]},
        },
        "required": ["type", "quantity", "weight_total", "weight_each", "description"],
    }


def _section_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


SYLLABUS_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "metadata": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "course_code": {"type": ["string", "null"]},
                "course_name": {"type": ["string", "null"]},
                "nrc": {"type": ["string", "null"]},
                "semester": {"type": ["string", "null"]},
                "academic_period": {"type": ["string", "null"]},
                "source_file": {"type": "string"},
            },
            "required": ["course_code", "course_name", "nrc", "semester", "academic_period", "source_file"],
        },
        "sections": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "evaluaciones_y_ponderaciones": _section_schema(
                    {
                        "found": {"type": "boolean"},
                        "page_numbers": {"type": "array", "items": {"type": "integer"}},
                        "raw_evidence": {"type": ["string", "null"]},
                        "structured_data": {
                            "anyOf": [
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "evaluations": {
                                            "type": "array",
                                            "items": _evaluation_item_schema(),
                                        },
                                    },
                                    "required": ["evaluations"],
                                },
                                {"type": "null"},
                            ]
                        },
                    },
                    ["found", "page_numbers", "raw_evidence", "structured_data"],
                ),
                "requisitos_aprobacion": _section_schema(
                    {
                        "found": {"type": "boolean"},
                        "page_numbers": {"type": "array", "items": {"type": "integer"}},
                        "raw_evidence": {"type": ["string", "null"]},
                        "structured_data": {
                            "anyOf": [
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "minimum_final_grade": {"type": ["number", "null"]},
                                        "minimum_exam_grade": {"type": ["number", "null"]},
                                        "automatic_failure_rules": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "grade_cap_rules": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "attendance_rules": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                    "required": [
                                        "minimum_final_grade",
                                        "minimum_exam_grade",
                                        "automatic_failure_rules",
                                        "grade_cap_rules",
                                        "attendance_rules",
                                    ],
                                },
                                {"type": "null"},
                            ]
                        },
                    },
                    ["found", "page_numbers", "raw_evidence", "structured_data"],
                ),
                "criterios_eximicion": _section_schema(
                    {
                        "found": {"type": "boolean"},
                        "page_numbers": {"type": "array", "items": {"type": "integer"}},
                        "raw_evidence": {"type": ["string", "null"]},
                        "structured_data": {
                            "anyOf": [
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "is_available": {"type": ["boolean", "null"]},
                                        "threshold": {"type": ["number", "null"]},
                                        "conditions": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                    "required": ["is_available", "threshold", "conditions"],
                                },
                                {"type": "null"},
                            ]
                        },
                    },
                    ["found", "page_numbers", "raw_evidence", "structured_data"],
                ),
                "nota_final": _section_schema(
                    {
                        "found": {"type": "boolean"},
                        "page_numbers": {"type": "array", "items": {"type": "integer"}},
                        "raw_evidence": {"type": ["string", "null"]},
                        "structured_data": {
                            "anyOf": [
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "presentation_grade_formula": {"type": ["string", "null"]},
                                        "final_grade_formula": {"type": ["string", "null"]},
                                        "presentation_weight": {"type": ["number", "null"]},
                                        "exam_weight": {"type": ["number", "null"]},
                                    },
                                    "required": [
                                        "presentation_grade_formula",
                                        "final_grade_formula",
                                        "presentation_weight",
                                        "exam_weight",
                                    ],
                                },
                                {"type": "null"},
                            ]
                        },
                    },
                    ["found", "page_numbers", "raw_evidence", "structured_data"],
                ),
            },
            "required": [
                "evaluaciones_y_ponderaciones",
                "requisitos_aprobacion",
                "criterios_eximicion",
                "nota_final",
            ],
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["metadata", "sections", "warnings"],
}

SYLLABUS_COMPARISON_SYSTEM_PROMPT = """
Eres un revisor académico experto en consistencia de syllabus universitarios.
Recibes JSON normalizados, uno por syllabus/NRC de un mismo curso.
Debes comparar todos los JSON juntos, no los textos completos ni comparaciones
pareadas documento a documento.

Reglas obligatorias:
- No inventes datos.
- No compares redacciones equivalentes como diferencias sustantivas.
- Reporta solo diferencias relevantes para evaluación, aprobación, eximición o
  cálculo de nota final.
- Clasifica como critica cualquier cambio que altere condiciones académicas.
- Clasifica como moderada una omisión, ambigüedad o regla incompleta.
- Clasifica como menor una diferencia de redacción, formato o estilo.
- Identifica el valor de la mayoría y los NRC outlier cuando exista patrón.
- Si un dato no puede determinarse con seguridad, usa null y agrega una
  advertencia en warnings.
- Devuelve exclusivamente JSON válido.
""".strip()


SYLLABUS_COMPARISON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "course": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "course_code": {"type": ["string", "null"]},
                "course_name": {"type": ["string", "null"]},
                "nrcs_compared": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["course_code", "course_name", "nrcs_compared"],
        },
        "summary": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "total_syllabus_compared": {"type": "integer"},
                "total_inconsistencies": {"type": "integer"},
                "most_deviating_nrc": {"type": ["string", "null"]},
                "severity_counts": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "critica": {"type": "integer"},
                        "moderada": {"type": "integer"},
                        "menor": {"type": "integer"},
                    },
                    "required": ["critica", "moderada", "menor"],
                },
                "possible_outlier": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "properties": {
                        "nrc": {"type": ["string", "null"]},
                        "alerts": {"type": "integer"},
                        "reason": {"type": ["string", "null"]},
                    },
                    "required": ["nrc", "alerts", "reason"],
                },
                "analysis_mode": {"type": "string"},
            },
            "required": [
                "total_syllabus_compared",
                "total_inconsistencies",
                "most_deviating_nrc",
                "severity_counts",
                "possible_outlier",
                "analysis_mode",
            ],
        },
        "inconsistencies": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "section": {"type": "string"},
                    "variable": {"type": "string"},
                    "severity": {"type": "string", "enum": ["critica", "moderada", "menor"]},
                    "description": {"type": "string"},
                    "values_by_nrc": {
                        "type": "object",
                        "additionalProperties": {"type": ["string", "number", "null"]},
                    },
                    "majority_value": {"type": ["string", "number", "null"]},
                    "outlier_nrcs": {"type": "array", "items": {"type": "string"}},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "nrc": {"type": "string"},
                                "page": {"type": ["integer", "null"]},
                                "text": {"type": ["string", "null"]},
                            },
                            "required": ["nrc", "page", "text"],
                        },
                    },
                    "suggested_action": {"type": "string"},
                },
                "required": [
                    "section",
                    "variable",
                    "severity",
                    "description",
                    "values_by_nrc",
                    "majority_value",
                    "outlier_nrcs",
                    "evidence",
                    "suggested_action",
                ],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["course", "summary", "inconsistencies", "warnings"],
}


def build_syllabus_extraction_user_prompt(
    *,
    syllabus_metadata: dict[str, Any],
    pages: list[dict[str, Any]],
) -> str:
    return f"""
Syllabus a analizar:
{json.dumps(syllabus_metadata, ensure_ascii=False, indent=2)}

Páginas extraídas por PyMuPDF con su número original:
{json.dumps(pages, ensure_ascii=False, indent=2)}

Identifica y normaliza solo estos apartados:
- Evaluaciones y Ponderaciones
- Requisitos de Aprobación
- Criterios de Eximición
- Nota Final de la Asignatura

Devuelve un JSON con la estructura solicitada por el esquema.
Reglas de normalización:
- Usa page_numbers para ubicar la evidencia real.
- raw_evidence debe ser breve y literal o casi literal.
- structured_data debe contener solo información académicamente relevante.
- Si no puedes determinar un valor, usa null y agrega una advertencia.
- Todo el contenido textual que produzcas en el JSON debe estar en español neutro.
- No incluyas texto fuera del JSON.
""".strip()


def build_syllabus_comparison_user_prompt(
    *,
    course_metadata: dict[str, Any],
    normalized_syllabi: list[dict[str, Any]],
) -> str:
    return f"""
Curso analizado:
{json.dumps(course_metadata, ensure_ascii=False, indent=2)}

JSON normalizados por syllabus/NRC:
{json.dumps(normalized_syllabi, ensure_ascii=False, indent=2)}

Compara todos los JSON juntos y devuelve un reporte agregado.
Requisitos:
- No hagas comparación pareada documento a documento.
- Detecta mayoría, outliers y diferencias sustantivas.
- Si varias redacciones significan lo mismo, no las marques como inconsistencia principal.
- Reporta solo diferencias relevantes para el curso.
- Si falta un dato, marca la omisión y su gravedad.
- Usa evidencia breve con NRC, página y texto.
- Todo el contenido textual que produzcas en el JSON debe estar en español neutro.
- Devuelve exclusivamente JSON.
""".strip()