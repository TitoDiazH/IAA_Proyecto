from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SectionPrompt:
    key: str
    name: str
    prompt: str


SECTION_EXTRACTION_SYSTEM_PROMPT = """
Eres un especialista en revisión académica de syllabus universitarios.
Tu tarea es extraer información estructurada de un apartado específico del syllabus.
No apruebas ni rechazas documentos. No evalúas calidad pedagógica.
Debes distinguir entre texto explícito, información inferida y ausencia de información.
Devuelve exclusivamente JSON compatible con el esquema solicitado.
""".strip()


SECTION_PROMPTS: list[SectionPrompt] = [
    SectionPrompt(
        key="general_info",
        name="Información General de la Asignatura",
        prompt="""
Analiza exclusivamente la información general de la asignatura.
Busca datos como nombre de la asignatura, periodo o año-semestre, carrera,
código del curso, NRC, créditos, módulos semanales, requisitos previos,
modalidad y semestre.

Extrae variables concretas usando estos nombres cuando aparezcan en el texto:
- nombreAsignatura
- periodo
- carrera
- codigoCurso
- nrc
- creditos
- modulosSemanales
- requisitosPrevios
- modalidad
- semestre

Si un campo no aparece explícitamente, marca el valor como no informado.
No inventes datos a partir del resto del documento.
""".strip(),
    ),
    SectionPrompt(
        key="evaluations",
        name="Evaluaciones y Ponderaciones",
        prompt="""
Analiza exclusivamente el apartado de Evaluaciones y Ponderaciones.
Busca aunque el syllabus use títulos alternativos como sistema de evaluación,
evaluaciones, ponderaciones, calificaciones o instrumentos evaluativos.

Extrae variables concretas:
- número de evaluaciones;
- tipo de cada evaluación;
- nombre o etiqueta de cada evaluación;
- ponderación porcentual de cada evaluación;
- existencia de examen;
- si el examen aparece como evaluación obligatoria, recuperativa o final;
- cualquier omisión, ambigüedad o contradicción interna relevante.

Cuando la información aparezca como tabla, reconstruye cada fila en el orden del
texto. Usa las columnas visibles para distinguir tipo, ponderación y
descripción.

No marques como diferencia académica una variación de redacción. En esta etapa
solo extraes datos estructurados y evidencia textual breve.
""".strip(),
    ),
    SectionPrompt(
        key="approval_requirements",
        name="Requisitos de Aprobación",
        prompt="""
Analiza exclusivamente los Requisitos de Aprobación.
Busca títulos alternativos como condiciones de aprobación, requisitos para aprobar,
aprobación de la asignatura o reglas de aprobación.

Extrae variables concretas:
- nota mínima de aprobación;
- requisitos mínimos para aprobar;
- requisitos para rendir examen;
- nota mínima para rendir examen;
- reglas de asistencia si afectan aprobación o derecho a examen;
- causales de reprobación;
- omisiones o ambigüedades que puedan afectar aprobación, examen o nota final.

No inventes reglas. Si una regla no aparece, declárala como no informada.
""".strip(),
    ),
    SectionPrompt(
        key="exemption",
        name="Criterios de Eximición",
        prompt="""
Analiza exclusivamente los Criterios de Eximición.
Busca títulos o frases equivalentes como eximición, eximirse, eximido,
exoneración de examen o liberación de examen.

Extrae variables concretas:
- si existe posibilidad de eximición;
- umbral numérico de eximición;
- condiciones adicionales para eximirse;
- evaluaciones consideradas para calcular el promedio previo;
- si la eximición depende de asistencia, nota mínima por evaluación u otro requisito;
- reglas ausentes o ambiguas.

Reconoce equivalencias semánticas: "promedio igual o superior a 5,5" y
"nota final previa igual o mayor a 5,5" pueden representar la misma regla si el
contexto confirma que ambas se refieren al umbral de eximición.
""".strip(),
    ),
    SectionPrompt(
        key="final_grade",
        name="Nota Final de la Asignatura",
        prompt="""
Analiza exclusivamente la Nota Final de la Asignatura.
Busca títulos alternativos como cálculo de nota final, fórmula de nota final,
calificación final, nota de presentación o NF.

Extrae variables concretas:
- fórmula exacta de cálculo de nota final;
- variables usadas en la fórmula;
- ponderación de examen en la nota final;
- ponderación de evaluaciones parciales;
- reglas de redondeo si aparecen;
- relación entre nota de presentación, examen y nota final;
- omisiones o ambigüedades que impidan calcular la nota final.

Mantén la fórmula tal como aparece y agrega una interpretación normalizada en
lenguaje académico si es necesario.
""".strip(),
    ),
]


COMPARISON_SYSTEM_PROMPT = """
Eres un revisor académico experto en consistencia de syllabus universitarios.
Comparas información estructurada extraída por IA desde distintos syllabus de un
mismo curso. Tu objetivo es identificar coincidencias, diferencias,
inconsistencias y elementos relevantes para revisión académica.

Reglas obligatorias:
- No apruebes ni rechaces syllabus.
- No evalúes calidad pedagógica.
- No reportes como alerta principal diferencias meramente formales.
- Distingue redacciones distintas que significan lo mismo de diferencias que
  cambian evaluación, aprobación, eximición o nota final.
- Si hay dos syllabus, reporta diferencias sin asumir cuál está correcto.
- Si hay tres o más syllabus, identifica el patrón general cuando exista y marca
  cuál NRC se aleja más del patrón.
- Usa gravedad "Crítica" para diferencias que afectan evaluación, aprobación,
  eximición o nota final.
- Usa gravedad "Moderada" para omisiones parciales, reglas incompletas o
  elementos que puedan generar confusión.
- Usa gravedad "Menor" para diferencias de redacción o formato. Estas pueden
  quedar registradas, pero no como alerta principal.

Devuelve exclusivamente JSON compatible con el esquema solicitado.
No uses información que no esté presente en los datos estructurados de entrada.
""".strip()


SECTION_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "section_name": {"type": "string"},
        "section_found": {"type": "boolean"},
        "confidence": {"type": "number"},
        "relevant_excerpt": {"type": "string"},
        "extracted_variables": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                    "normalized_value": {"type": "string"},
                    "evidence": {"type": "string"},
                    "academic_relevance": {"type": "string"},
                },
                "required": [
                    "name",
                    "value",
                    "normalized_value",
                    "evidence",
                    "academic_relevance",
                ],
            },
        },
        "missing_or_ambiguous_elements": {
            "type": "array",
            "items": {"type": "string"},
        },
        "academic_interpretation": {"type": "string"},
    },
    "required": [
        "section_name",
        "section_found",
        "confidence",
        "relevant_excerpt",
        "extracted_variables",
        "missing_or_ambiguous_elements",
        "academic_interpretation",
    ],
}


COMPARISON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "analysis_mode": {"type": "string", "enum": ["pairwise", "group_pattern"]},
        "compared_nrcs": {"type": "array", "items": {"type": "string"}},
        "overall_summary": {"type": "string"},
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
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "nrc": {"type": "string"},
                "alert_count": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["nrc", "alert_count", "reason"],
        },
        "inconsistencies": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "section": {"type": "string"},
                    "variable": {"type": "string"},
                    "difference": {"type": "string"},
                    "involved_nrcs": {"type": "array", "items": {"type": "string"}},
                    "severity": {"type": "string", "enum": ["Crítica", "Moderada", "Menor"]},
                    "priority_rationale": {"type": "string"},
                    "suggestion": {"type": "string"},
                    "evidence": {"type": "string"},
                    "is_main_alert": {"type": "boolean"},
                },
                "required": [
                    "section",
                    "variable",
                    "difference",
                    "involved_nrcs",
                    "severity",
                    "priority_rationale",
                    "suggestion",
                    "evidence",
                    "is_main_alert",
                ],
            },
        },
    },
    "required": [
        "analysis_mode",
        "compared_nrcs",
        "overall_summary",
        "severity_counts",
        "possible_outlier",
        "inconsistencies",
    ],
}


COMBINED_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        # Include all comparison fields
        **COMPARISON_SCHEMA["properties"],
        # Add extracted sections by NRC
        "extracted_sections_by_nrc": {
            "type": "object",
            "additionalProperties": SECTION_EXTRACTION_SCHEMA,
        },
    },
    "required": COMPARISON_SCHEMA["required"] + ["extracted_sections_by_nrc"],
}

