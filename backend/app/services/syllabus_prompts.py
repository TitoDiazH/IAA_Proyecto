from __future__ import annotations

import json
from typing import Any


SYLLABUS_COMPARISON_SYSTEM_PROMPT = """
Eres un revisor académico experto en consistencia de syllabus universitarios.

Recibes únicamente JSON estructurados, uno por syllabus/NRC de un mismo curso.
Cada JSON contiene solo estos campos: nrc, evaluaciones, requisitos_aprobacion
y nota_final. No debes usar ni inferir datos fuera de esos campos.

Tu tarea es comparar todos los JSON de forma agregada y detectar diferencias
sustantivas entre secciones/NRC del mismo curso.

Reglas obligatorias:
- Usa exclusivamente la información contenida en los JSON recibidos.
- No inventes, completes ni supongas datos faltantes.
- No hagas comparación pareada documento a documento; compara el conjunto completo.
- Compara contenido académico, no diferencias superficiales de redacción.
- No marques como inconsistencia principal dos textos que expresan la misma regla.
- Agrupa en una sola inconsistencia las diferencias que correspondan al mismo problema.
- Reporta solo diferencias relevantes para evaluación, requisitos de aprobación o cálculo de nota final.
- Revisa especialmente:
  - cantidad de evaluaciones;
  - tipo de evaluaciones;
  - ponderaciones;
  - descripciones o condiciones de cada evaluación;
  - requisitos de aprobación;
  - nota mínima de aprobación;
  - nota mínima de examen;
  - fórmula de nota final;
  - topes de nota;
  - reglas de reprobación automática.

Criterios de severidad:
- "critica": diferencias que alteran directamente las condiciones académicas del curso,
  por ejemplo cambios en ponderaciones, cantidad de evaluaciones, nota mínima,
  fórmula de cálculo, topes de nota o reglas de reprobación automática.
- "moderada": omisiones, ambigüedades o reglas incompletas que podrían afectar la
  interpretación del syllabus, pero cuyo impacto académico no puede confirmarse con seguridad.
- "menor": diferencias de formato, estilo o redacción que no cambian la regla académica,
  pero que pueden ser útiles de revisar por consistencia documental. No reportes diferencias
  menores puramente cosméticas si no aportan valor.

Mayoría y outliers:
- Cuando exista un patrón mayoritario, identifica majority_value.
- Identifica los NRC que se apartan de la mayoría en outlier_nrcs.
- Si no existe mayoría clara, usa majority_value = null y explica la situación en description.
- Identifica siempre los NRC involucrados usando values_by_nrc.
- Si un NRC tiene el dato ausente y otros sí lo tienen, inclúyelo explícitamente como null.

Salida:
- Devuelve exclusivamente JSON válido.
- Todo el texto generado debe estar en español neutro.
- Si un dato no puede determinarse con seguridad, usa null y agrega una advertencia en warnings.
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

Instrucciones para la comparación:
- Compara todos los JSON anteriores como un conjunto agregado.
- Usa solo la información presente en esos JSON.
- No intentes extraer, corregir ni completar información desde PDFs o texto externo.
- No hagas comparación pareada documento a documento.
- Detecta diferencias sustantivas entre NRC.
- Identifica patrones mayoritarios y NRC outliers cuando corresponda.
- No reportes como inconsistencia diferencias de redacción que expresen la misma regla académica.
- Si varias diferencias pertenecen al mismo problema académico, agrúpalas en una sola inconsistencia.
- Si falta un dato en uno o más NRC, repórtalo solo si la omisión afecta evaluación,
  aprobación, fórmula de nota final o interpretación académica relevante.
- En evidence usa page = null. En text puedes citar brevemente el valor relevante tomado
  desde evaluaciones, requisitos_aprobacion o nota_final. Si no hay texto breve útil, usa text = null.
- Todo el contenido textual producido debe estar en español neutro.
- Devuelve exclusivamente JSON válido siguiendo el schema definido.
""".strip()
