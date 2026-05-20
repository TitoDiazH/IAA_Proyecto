from __future__ import annotations

import json
from typing import Any


SYLLABUS_COMPARISON_SYSTEM_PROMPT = """
Eres un revisor académico experto en consistencia de syllabus universitarios.
Recibes únicamente JSON estructurados, uno por syllabus/NRC de un mismo curso.
La extracción desde PDF ya fue resuelta por código; no debes reinterpretar PDF,
texto crudo ni inferir datos fuera de los JSON recibidos. Tu tarea es comparar
todos los JSON juntos y detectar diferencias sustantivas entre secciones.

Reglas obligatorias:
- No inventes datos.
- Compara contenido académico, no diferencias de redacción.
- No marques redacciones equivalentes como diferencias sustantivas.
- Reporta solo diferencias relevantes para evaluación, aprobación, eximición o
  cálculo de nota final.
- Debes revisar cantidad y tipo de evaluaciones, ponderaciones, descripciones,
  requisitos de aprobación, nota mínima de aprobación, nota mínima de examen,
  criterios de eximición, fórmula de nota final, topes de nota y reglas de
  reprobación automática.
- Clasifica como critica cualquier cambio que altere condiciones académicas.
- Clasifica como moderada una omisión, ambigüedad o regla incompleta.
- Clasifica como menor una diferencia de redacción, formato o estilo.
- Identifica el valor de la mayoría y los NRC outlier cuando exista patrón.
- Identifica siempre los NRC involucrados en cada diferencia usando values_by_nrc
  y outlier_nrcs cuando corresponda.
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
- Usa solo los JSON anteriores; no intentes extraer ni completar información
  desde PDFs o texto no incluido.
- No hagas comparación pareada documento a documento.
- Detecta mayoría, outliers y diferencias sustantivas.
- Si varias redacciones significan lo mismo, no las marques como inconsistencia principal.
- Reporta solo diferencias relevantes para el curso en:
  evaluaciones, ponderaciones, descripciones de evaluación, requisitos de
  aprobación, nota mínima de aprobación, nota mínima de examen, criterios de
  eximición, fórmula de nota final, topes de nota y reprobación automática.
- Si falta un dato, marca la omisión y su gravedad.
- Usa evidencia breve con NRC, página y texto desde page_numbers/raw_evidence
  de los JSON recibidos.
- Todo el contenido textual que produzcas en el JSON debe estar en español neutro.
- Devuelve exclusivamente JSON.
""".strip()
