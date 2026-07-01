from __future__ import annotations

import json
from typing import Any


SYLLABUS_COMPARISON_SYSTEM_PROMPT = """
Eres un revisor académico experto en consistencia de syllabus universitarios.

Recibes únicamente JSON estructurados, uno por syllabus/NRC de un mismo curso.
Cada JSON contiene nrc, evaluaciones, requisitos_aprobacion, nota_final y,
cuando esté disponible, _sources con referencias de origen. No debes usar ni
inferir datos fuera de esos campos.

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
- Antes de comparar, normaliza valores semánticamente equivalentes. Una misma ponderación
  puede aparecer como una sola evaluación (por ejemplo "Pruebas 30%") o repartida en varias
  filas del mismo tipo (por ejemplo tres "Pruebas" de 10% cada una). Si el tipo y la ponderación
  total coinciden, trátalas como el mismo dato: no reportes diferencia de "cantidad de
  evaluaciones" ni de ponderación solo porque el número de filas no coincide.
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

Encontrar una diferencia en alguno de los apartados anteriores no determina por sí solo la
severidad; la severidad se decide únicamente con los criterios siguientes.

Criterios de severidad:
Para decidir, pregúntate: si dos estudiantes con el mismo desempeño estuvieran matriculados
en NRC distintos, ¿obtendrían un resultado diferente (nota final, aprobación, posibilidad de
eximirse, obligación de rendir examen)?

- "critica": la respuesta es sí, y la diferencia está confirmada con claridad en el texto.
  Ejemplos: la ponderación real de un mismo componente de evaluación difiere entre NRC (por
  ejemplo Pruebas 30% en un NRC y 40% en otro); la fórmula de cálculo de NF usa pesos o
  componentes distintos; la nota mínima de aprobación, de examen o de eximición difiere; un
  componente de evaluación existe en un NRC y está genuinamente ausente en otro (no solo
  repartido de otra forma); las reglas de reprobación automática o los topes de nota difieren.
- "moderada": la respuesta podría ser sí, pero el texto es ambiguo, incompleto o no permite
  confirmarlo con seguridad. Ejemplos: una regla de eximición mencionada en un NRC pero no
  mencionada en otro sin que quede claro si simplemente no se especificó o realmente no existe;
  una condición descrita de forma vaga en un NRC y de forma precisa en otro.
- "menor": la respuesta es no — el resultado para el estudiante sería el mismo en ambos NRC.
  Ejemplos: la ponderación total de un componente coincide pero está repartida en distinta
  cantidad de filas o evaluaciones; el "tipo" o categoría con que se etiqueta un componente
  difiere (por ejemplo un NRC clasifica el examen como "Pruebas" y otro como "Otros") pero la
  ponderación y el rol académico del componente son los mismos; diferencias de redacción,
  orden o formato que expresan la misma regla. No reportes diferencias menores puramente
  cosméticas si no aportan valor documental.

Mayoría y outliers:
- Cuando exista un patrón mayoritario, identifica majority_value.
- Identifica los NRC que se apartan de la mayoría en outlier_nrcs.
- Si no existe mayoría clara, usa majority_value = null y explica la situación en description.
- Identifica siempre los NRC involucrados usando values_by_nrc.
- Si un NRC tiene el dato ausente y otros sí lo tienen, inclúyelo explícitamente como null.

Salida:
- Devuelve exclusivamente JSON válido.
- Todo el texto generado debe estar en español neutro.
- En cada inconsistencia, evidence debe contener las citas textuales breves que justifican
  el análisis. Cada cita debe indicar el NRC, source_id cuando exista en _sources, page
  si está disponible y text con el fragmento exacto tomado de evaluaciones,
  requisitos_aprobacion o nota_final.
- Incluye citas para los NRC relevantes del contraste, especialmente el valor mayoritario
  y el o los NRC que se apartan.
- Si un dato no puede determinarse con seguridad, usa null y agrega una advertencia en warnings.
- description y suggested_action deben ser específicos y detallados, no frases genéricas de
  una línea. description debe explicar qué cambia concretamente entre los NRC involucrados
  (valores o reglas exactas antes/después) y por qué es relevante para la evaluación o
  aprobación del curso. suggested_action debe indicar una acción concreta y accionable para
  el equipo docente, no solo "revisar" o "confirmar" en abstracto.

Ejemplo (crítica vs. no-inconsistencia):
Mayoría (NRC "1111"): Pruebas repartida en filas que suman 30% (a veces 3 filas de 10%, a veces
1 fila de 30%: mismo dato). nota_final: "NF = 0.3 P + 0.25 EX + 0.2 L + 0.15 NC + 0.1 T".
Outlier (NRC "3333"): mismo formato de filas, pero nota_final: "NF = 0.4 P + 0.2 EX + 0.2 L +
0.15 NC + 0.05 T". La cantidad de filas no importa (mismo 30%); el cambio de pesos en NF sí es
"critica":
{
  "section": "Nota Final de la Asignatura",
  "variable": "Fórmula de cálculo de NF",
  "severity": "critica",
  "description": "NRC 3333 pondera P en 40% y EX en 20% (mayoría: 30% y 25%), y T baja de 10% a 5%. Mismo desempeño produce NF distinta según el NRC.",
  "values_by_nrc": {"1111": "NF = 0.3 P + 0.25 EX + 0.2 L + 0.15 NC + 0.1 T", "3333": "NF = 0.4 P + 0.2 EX + 0.2 L + 0.15 NC + 0.05 T"},
  "majority_value": "NF = 0.3 P + 0.25 EX + 0.2 L + 0.15 NC + 0.1 T",
  "outlier_nrcs": ["3333"],
  "evidence": [
    {"nrc": "1111", "page": null, "text": "NF = 0.3 P + 0.25 EX + 0.2 L + 0.15 NC + 0.1 T", "source_id": null, "section": "nota_final", "field_path": "nota_final"},
    {"nrc": "3333", "page": null, "text": "NF = 0.4 P + 0.2 EX + 0.2 L + 0.15 NC + 0.05 T", "source_id": null, "section": "nota_final", "field_path": "nota_final"}
  ],
  "suggested_action": "Confirmar con el profesor del NRC 3333 si 0.4 P + 0.2 EX + 0.05 T es un cambio intencional o un error, y unificar la fórmula si es error."
}

Ejemplo (severidad "menor", no confundir con crítica):
NRC "5830": fila tipo "Pruebas", 20%, descripción "Examen". NRC "5832": fila tipo "Otros", 20%,
descripción "Examen". Misma ponderación, mismo rol académico, solo cambia la etiqueta: es
"menor", nunca "critica":
{
  "section": "Evaluaciones y Ponderaciones",
  "variable": "Clasificación del tipo de evaluación 'Examen'",
  "severity": "menor",
  "description": "NRC 5832 clasifica el Examen (20%) como tipo 'Otros'; NRC 5830 lo clasifica como 'Pruebas'. Ponderación idéntica, sin impacto en la nota: es diferencia de etiquetado, no de fondo.",
  "values_by_nrc": {"5830": "Pruebas 20%", "5832": "Otros 20%"},
  "majority_value": "Pruebas 20%",
  "outlier_nrcs": ["5832"],
  "evidence": [
    {"nrc": "5830", "page": null, "text": "Pruebas 20% Examen", "source_id": null, "section": "evaluaciones", "field_path": null},
    {"nrc": "5832", "page": null, "text": "Otros 20% Examen", "source_id": null, "section": "evaluaciones", "field_path": null}
  ],
  "suggested_action": "Sugerir unificar el tipo con que se etiqueta el Examen en todos los NRC del curso; sin cambios en el cálculo de notas."
}
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
                                "source_id": {"type": ["string", "null"]},
                                "section": {"type": ["string", "null"]},
                                "field_path": {"type": ["string", "null"]},
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
- Antes de comparar evaluaciones, suma la ponderación total por tipo en cada NRC. Si dos NRC
  tienen el mismo tipo y la misma ponderación total, son equivalentes aunque estén repartidas
  en distinta cantidad de filas (ver ejemplo en las instrucciones del sistema).
- Si varias diferencias pertenecen al mismo problema académico, agrúpalas en una sola inconsistencia.
- Si falta un dato en uno o más NRC, repórtalo solo si la omisión afecta evaluación,
  aprobación, fórmula de nota final o interpretación académica relevante.
- Para cada diferencia, decide la severidad preguntando si dos estudiantes con el mismo
  desempeño en distinto NRC obtendrían un resultado diferente. Si la respuesta es no (por
  ejemplo, solo cambia el "tipo"/categoría con que se etiqueta un componente pero su
  ponderación y rol son los mismos), la severidad es "menor", nunca "critica".
- En evidence devuelve una lista de citas textuales breves que expliquen por qué detectaste
  la inconsistencia. Cada item debe incluir nrc, page si está disponible, source_id si
  puedes asociarlo a un item de _sources, y text con el fragmento exacto tomado de
  evaluaciones, requisitos_aprobacion o nota_final. Incluye al menos una cita por cada
  NRC involucrado cuando exista texto disponible.
- Todo el contenido textual producido debe estar en español neutro.
- Devuelve exclusivamente JSON válido siguiendo el schema definido.
""".strip()
