from __future__ import annotations

import json
from typing import Any

from app.services.ai_client import JsonCompletionClient


CONDITIONS_EXPORT_SYSTEM_PROMPT = """
Eres un analista académico que transforma reglas de syllabus en celdas breves
para una planilla de condiciones de aprobación.

Tu tarea es extraer solo fórmulas, umbrales y reglas operativas. No copies
párrafos completos. No inventes datos. Si un dato no aparece, usa string vacío,
salvo requisitos_exencion, donde puedes usar "-" si no existe exención.

Formato esperado:
- requisitos_aprobacion: condiciones compactas separadas por punto y coma.
  Ejemplo: "NP>=3; NE>=3; NF>=4".
- requisitos_exencion: umbral o condición breve de exención.
  Ejemplo: "NP>=5.5" o "-".
- nota_final: fórmula principal de nota final.
  Ejemplo: "NF=0.7NP+0.3NE".
- nota_final_reprobados: reglas condicionales de reprobación/tope.
  Ejemplo: "Si NP<3 -> NF=NP; Si NE<3 -> NF=min(3.9,NF)".
- otros_criterios: reglas relevantes que no entren en los campos anteriores.

Devuelve exclusivamente JSON válido.
""".strip()


CONDITIONS_EXPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "nrc": {"type": "string"},
                    "requisitos_aprobacion": {"type": "string"},
                    "requisitos_exencion": {"type": "string"},
                    "nota_final": {"type": "string"},
                    "nota_final_reprobados": {"type": "string"},
                    "otros_criterios": {"type": "string"},
                },
                "required": [
                    "nrc",
                    "requisitos_aprobacion",
                    "requisitos_exencion",
                    "nota_final",
                    "nota_final_reprobados",
                    "otros_criterios",
                ],
            },
        }
    },
    "required": ["rows"],
}


def enrich_syllabi_with_conditions_export(
    normalized_syllabi_by_nrc: dict[str, Any],
    client: JsonCompletionClient,
) -> dict[str, Any]:
    payload = [
        {
            "nrc": nrc,
            "evaluaciones": syllabus.get("evaluaciones", []),
            "requisitos_aprobacion": syllabus.get("requisitos_aprobacion", ""),
            "criterios_eximicion": syllabus.get("criterios_eximicion", ""),
            "nota_final": syllabus.get("nota_final", ""),
        }
        for nrc, syllabus in normalized_syllabi_by_nrc.items()
        if isinstance(syllabus, dict)
    ]
    if not payload:
        return normalized_syllabi_by_nrc

    result = client.complete_json(
        system_prompt=CONDITIONS_EXPORT_SYSTEM_PROMPT,
        user_prompt=f"""
Extrae campos de planilla para estos syllabus:
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip(),
        schema_name="conditions_export",
        schema=CONDITIONS_EXPORT_SCHEMA,
    )

    rows = result.get("rows") if isinstance(result, dict) else []
    by_nrc = {
        str(row.get("nrc")): {
            "requisitos_aprobacion": _clean(row.get("requisitos_aprobacion")),
            "requisitos_exencion": _clean(row.get("requisitos_exencion")),
            "nota_final": _clean(row.get("nota_final")),
            "nota_final_reprobados": _clean(row.get("nota_final_reprobados")),
            "otros_criterios": _clean(row.get("otros_criterios")),
        }
        for row in rows
        if isinstance(row, dict) and str(row.get("nrc") or "").strip()
    }

    for nrc, fields in by_nrc.items():
        if isinstance(normalized_syllabi_by_nrc.get(nrc), dict):
            normalized_syllabi_by_nrc[nrc]["conditions_export"] = fields

    return normalized_syllabi_by_nrc


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())
