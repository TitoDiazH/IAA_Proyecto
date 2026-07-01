from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import time
from typing import Any

from app.config import get_settings
from app.services.ai_client import JsonCompletionClient


CONDITIONS_EXPORT_SYSTEM_PROMPT = """
Eres un analista académico experto en extraer condiciones de aprobación desde
syllabus universitarios.

Debes procesar un único syllabus/NRC por llamada. Usa exclusivamente los
apartados entregados: evaluaciones, requisitos_aprobacion y nota_final.
No compares con otros NRC y no inventes reglas ausentes.

Los documentos no tienen un apartado independiente llamado "Criterios de
Eximición". Las reglas de eximición, requisitos para rendir examen, fórmulas
auxiliares, reglas especiales y otros criterios pueden aparecer dentro de
requisitos_aprobacion o nota_final. Clasifica cada regla por su significado,
no por el apartado donde aparece.

Reglas estrictas:
- Devuelve exclusivamente JSON válido según el esquema.
- Si una fórmula o condición no aparece de forma explícita, usa null.
- Nunca uses 0, "NF = 0" ni cadenas vacías como reemplazo de información faltante.
- Extrae la fórmula de nota final solo si el texto indica explícitamente cómo calcular NF
  o la nota final. Puedes convertir texto explícito como "70% NP y 30% EX" a
  "NF = 0.7*NP + 0.3*EX", pero solo si porcentajes y componentes aparecen en el texto.
- Conserva decimales con punto, por ejemplo 0.7, 3.9, 5.5.
- Diferencia requisitos de aprobación, requisitos de exención y reglas de cálculo.
- En requisitos_exencion incluye condiciones para eximirse del examen, aunque aparezcan
  en requisitos_aprobacion o nota_final.
- En nota_final_reprobados incluye topes o reglas especiales, por ejemplo:
  "Si EX < 3.0 -> reprueba" o "Si NF calculada >= 4.0 y EX < 3.0 -> NF = 3.9".
- En otros_criterios incluye reglas relevantes que no sean requisitos de aprobación,
  exención ni fórmula principal, por ejemplo requisitos para rendir examen o fórmulas
  auxiliares como NP.
- En evidencia_textual incluye fragmentos breves y literales que justifiquen cada campo
  extraído. No incluyas evidencia para campos null.
- confianza_extraccion debe estar entre 0 y 1. Baja la confianza si el texto es ambiguo,
  incompleto o si la fórmula solo puede inferirse parcialmente.
- Es común que requisitos_aprobacion y nota_final repitan el mismo texto casi palabra por
  palabra. En ese caso úsalos como una sola fuente de información, no los compares entre sí
  ni los trates como datos independientes. Si en un caso excepcional ambos apartados se
  contradicen en un mismo dato, prioriza nota_final para la fórmula de cálculo y
  requisitos_aprobacion para condiciones de aprobación/exención, y agrega una advertencia.

Formato de campos:
- requisitos_aprobacion: condiciones compactas separadas por punto y coma.
- requisitos_exencion: condición breve de exención/eximición, o null si no existe o no se especifica.
- formula_nota_final: fórmula principal de cálculo, por ejemplo "NF = 0.7 NP + 0.3 EX".
- nota_final_reprobados: reglas de reprobación automática o tope de nota.
- otros_criterios: criterios relevantes que no entren en los campos anteriores.

Ejemplo:
Texto relevante: "NF = 0.5 P + 0.2 NC + 0.1 L + 0.2 EX. Si EX < 3.0 reprueba.
Si EX < 3.0 y NF calculada >= 4.0, la NF queda 3.9. Exime con NP >= 5.5."
Salida:
{
  "nrc": "1234",
  "requisitos_aprobacion": null,
  "requisitos_exencion": "NP >= 5.5",
  "formula_nota_final": "NF = 0.5 P + 0.2 NC + 0.1 L + 0.2 EX",
  "nota_final_reprobados": "Si EX < 3.0 -> reprueba; Si EX < 3.0 y NF calculada >= 4.0 -> NF = 3.9",
  "otros_criterios": null,
  "evidencia_textual": [
    {"campo": "formula_nota_final", "fragmento": "NF = 0.5 P + 0.2 NC + 0.1 L + 0.2 EX"},
    {"campo": "nota_final_reprobados", "fragmento": "Si EX < 3.0 reprueba"},
    {"campo": "requisitos_exencion", "fragmento": "Exime con NP >= 5.5"}
  ],
  "confianza_extraccion": 0.95,
  "advertencias": []
}

Ejemplo con fórmula condicional (confianza media):
Texto relevante: "NP=(P1+P2+P3+P4)/4. Si NP y EX >= 3.0: NF=0.7*NP+0.3*EX. Si NP < 3.0: NF = NP.
Si EX < 3.0 y 0.7*NP+0.3*EX >= 4.0: NF = 3.9. Se exime con NP >= 5.5."
Salida:
{
  "nrc": "5678",
  "requisitos_aprobacion": "NP >= 3.0 para presentarse a examen; NF >= 4.0 y EX >= 3.0 para aprobar",
  "requisitos_exencion": "NP >= 5.5",
  "formula_nota_final": "NF = 0.7*NP + 0.3*EX",
  "nota_final_reprobados": "Si NP < 3.0 -> NF = NP; Si EX < 3.0 y NF>=4.0 -> NF = 3.9",
  "otros_criterios": "NP = (P1+P2+P3+P4)/4",
  "evidencia_textual": [
    {"campo": "formula_nota_final", "fragmento": "Si NP y EX >= 3.0: NF=0.7*NP+0.3*EX"},
    {"campo": "nota_final_reprobados", "fragmento": "NF = 3.9"},
    {"campo": "requisitos_exencion", "fragmento": "Se exime con NP >= 5.5"}
  ],
  "confianza_extraccion": 0.75,
  "advertencias": ["Fórmula con ramas condicionales adicionales; revisar manualmente si se requiere el detalle completo."]
}
""".strip()


BATCH_CONDITIONS_EXPORT_SYSTEM_PROMPT = f"""
{CONDITIONS_EXPORT_SYSTEM_PROMPT}

Modo batch:
- Recibirás varios syllabus/NRC del mismo curso.
- Extrae cada NRC de forma independiente.
- No uses reglas de un NRC para completar otro.
- Devuelve un objeto con `rows`, donde cada item cumple el mismo formato de salida.
""".strip()


CONDITIONS_EXPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "nrc": {"type": "string"},
        "requisitos_aprobacion": {"type": ["string", "null"]},
        "requisitos_exencion": {"type": ["string", "null"]},
        "formula_nota_final": {"type": ["string", "null"]},
        "nota_final_reprobados": {"type": ["string", "null"]},
        "otros_criterios": {"type": ["string", "null"]},
        "evidencia_textual": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "campo": {"type": "string"},
                    "fragmento": {"type": "string"},
                },
                "required": ["campo", "fragmento"],
            },
        },
        "confianza_extraccion": {"type": "number"},
        "advertencias": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "nrc",
        "requisitos_aprobacion",
        "requisitos_exencion",
        "formula_nota_final",
        "nota_final_reprobados",
        "otros_criterios",
        "evidencia_textual",
        "confianza_extraccion",
        "advertencias",
    ],
}


BATCH_CONDITIONS_EXPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "rows": {
            "type": "array",
            "items": CONDITIONS_EXPORT_SCHEMA,
        },
    },
    "required": ["rows"],
}


def enrich_syllabi_with_conditions_export(
    normalized_syllabi_by_nrc: dict[str, Any],
    client: JsonCompletionClient,
) -> dict[str, Any]:
    payloads = [
        _build_payload(nrc, syllabus)
        for nrc, syllabus in normalized_syllabi_by_nrc.items()
        if isinstance(syllabus, dict)
    ]
    if not payloads:
        return normalized_syllabi_by_nrc

    settings = get_settings()
    if _should_use_batch_extraction(payloads, settings):
        try:
            results = _extract_conditions_batch(payloads, client)
        except Exception:
            results = _extract_conditions_many(payloads, client, settings)
    else:
        results = _extract_conditions_many(payloads, client, settings)

    for result in results:
        nrc = str(result.get("nrc") or "").strip()
        if isinstance(normalized_syllabi_by_nrc.get(nrc), dict):
            normalized_syllabi_by_nrc[nrc]["conditions_export"] = result

    return normalized_syllabi_by_nrc


def _should_use_batch_extraction(payloads: list[dict[str, Any]], settings: Any) -> bool:
    if len(payloads) <= 1:
        return False

    max_syllabi = int(getattr(settings, "conditions_export_batch_max_syllabi", 3) or 0)
    max_chars = int(getattr(settings, "conditions_export_batch_max_chars", 12000) or 0)
    if max_syllabi <= 0 or max_chars <= 0 or len(payloads) > max_syllabi:
        return False

    payload_size = len(json.dumps(payloads, ensure_ascii=False))
    return payload_size <= max_chars


def _extract_conditions_many(
    payloads: list[dict[str, Any]],
    client: JsonCompletionClient,
    settings: Any,
) -> list[dict[str, Any]]:
    max_workers = max(1, min(int(settings.conditions_export_max_workers or 1), len(payloads)))

    if max_workers == 1:
        return [_extract_conditions_for_syllabus(payload, client) for payload in payloads]

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_by_nrc = {
            executor.submit(_extract_conditions_for_syllabus, payload, client): payload["nrc"]
            for payload in payloads
        }
        for future in as_completed(future_by_nrc):
            nrc = future_by_nrc[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(_failed_conditions_export(nrc, exc))

    return results


def _build_payload(nrc: str, syllabus: dict[str, Any]) -> dict[str, Any]:
    return {
        "nrc": str(nrc),
        "evaluaciones": syllabus.get("evaluaciones", []),
        "requisitos_aprobacion": syllabus.get("requisitos_aprobacion", ""),
        "nota_final": syllabus.get("nota_final", ""),
    }


def _extract_conditions_for_syllabus(payload: dict[str, Any], client: JsonCompletionClient) -> dict[str, Any]:
    settings = get_settings()
    max_retries = int(settings.analysis_max_retries or 3)
    delay_seconds = int(settings.analysis_retry_delay_seconds or 30)
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            result = client.complete_json(
                system_prompt=CONDITIONS_EXPORT_SYSTEM_PROMPT,
                user_prompt=build_conditions_extraction_user_prompt(payload),
                schema_name="conditions_export",
                schema=CONDITIONS_EXPORT_SCHEMA,
            )
            return _normalize_conditions_result(payload["nrc"], result)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_retries:
                break
            time.sleep(delay_seconds)

    return _failed_conditions_export(payload["nrc"], last_exc)


def _extract_conditions_batch(payloads: list[dict[str, Any]], client: JsonCompletionClient) -> list[dict[str, Any]]:
    settings = get_settings()
    max_retries = int(settings.analysis_max_retries or 3)
    delay_seconds = int(settings.analysis_retry_delay_seconds or 30)
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            result = client.complete_json(
                system_prompt=BATCH_CONDITIONS_EXPORT_SYSTEM_PROMPT,
                user_prompt=build_conditions_batch_extraction_user_prompt(payloads),
                schema_name="conditions_export_batch",
                schema=BATCH_CONDITIONS_EXPORT_SCHEMA,
            )
            rows = result.get("rows") if isinstance(result, dict) else None
            if not isinstance(rows, list):
                raise ValueError("La extracción batch no devolvió una lista `rows`.")
            return _normalize_batch_conditions_result(payloads, rows)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_retries:
                break
            time.sleep(delay_seconds)

    raise RuntimeError("No fue posible extraer condiciones en modo batch.") from last_exc


def build_conditions_extraction_user_prompt(payload: dict[str, Any]) -> str:
    return f"""
Extrae las condiciones de aprobación para este único syllabus/NRC.

Syllabus:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Instrucciones:
- Busca la fórmula de nota final tanto en `nota_final` como en `requisitos_aprobacion`
  si la sección de nota final está incompleta.
- La eximición puede estar mencionada dentro de `requisitos_aprobacion` o `nota_final`.
- Los otros criterios también pueden estar mencionados dentro de esos dos apartados.
- Clasifica las reglas por significado, no por la sección donde aparecen.
- Si la fórmula no está explícita o no es convertible desde porcentajes y componentes
  explícitos, devuelve formula_nota_final = null.
- Si hay una regla de nota máxima por reprobar un mínimo, colócala en nota_final_reprobados.
- Incluye evidencia textual breve para cada campo no nulo.
""".strip()


def build_conditions_batch_extraction_user_prompt(payloads: list[dict[str, Any]]) -> str:
    return f"""
Extrae las condiciones de aprobación para estos syllabus/NRC.

Syllabus:
{json.dumps(payloads, ensure_ascii=False, indent=2)}

Instrucciones:
- Procesa cada NRC de forma independiente.
- Devuelve exactamente un item en `rows` por cada NRC recibido.
- Busca la fórmula de nota final tanto en `nota_final` como en `requisitos_aprobacion`
  si la sección de nota final está incompleta.
- La eximición puede estar mencionada dentro de `requisitos_aprobacion` o `nota_final`.
- Los otros criterios también pueden estar mencionados dentro de esos dos apartados.
- Clasifica las reglas por significado, no por la sección donde aparecen.
- Si la fórmula no está explícita o no es convertible desde porcentajes y componentes
  explícitos, devuelve formula_nota_final = null.
- Si hay una regla de nota máxima por reprobar un mínimo, colócala en nota_final_reprobados.
- Incluye evidencia textual breve para cada campo no nulo.
""".strip()


def _normalize_batch_conditions_result(
    payloads: list[dict[str, Any]],
    rows: list[Any],
) -> list[dict[str, Any]]:
    expected_nrcs = [payload["nrc"] for payload in payloads]
    normalized_by_nrc = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        nrc = str(row.get("nrc") or "").strip()
        if not nrc:
            continue
        normalized_by_nrc[nrc] = _normalize_conditions_result(nrc, row)

    return [
        normalized_by_nrc.get(nrc)
        or _failed_conditions_export(nrc, RuntimeError("La extracción batch omitió este NRC."))
        for nrc in expected_nrcs
    ]


def _normalize_conditions_result(nrc: str, result: dict[str, Any]) -> dict[str, Any]:
    formula = _clean_formula_field(result.get("formula_nota_final"))
    failed_rules = _clean_rule_field(result.get("nota_final_reprobados") or result.get("nota_final_reprobacion"))
    approval = _clean_nullable_text(result.get("requisitos_aprobacion"))
    exemption = _clean_nullable_text(result.get("requisitos_exencion") or result.get("requisitos_eximicion"))
    other = _clean_nullable_text(result.get("otros_criterios"))
    evidence = _normalize_evidence(result.get("evidencia_textual"))
    warnings = [text for item in result.get("advertencias", []) if (text := _clean_nullable_text(item))]
    confidence = _normalize_confidence(result.get("confianza_extraccion"))

    return {
        "nrc": str(result.get("nrc") or nrc),
        "requisitos_aprobacion": approval,
        "requisitos_exencion": exemption,
        "formula_nota_final": formula,
        "nota_final_reprobados": failed_rules,
        "otros_criterios": other,
        "evidencia_textual": evidence,
        "confianza_extraccion": confidence,
        "advertencias": warnings,
    }


def _failed_conditions_export(nrc: str, exc: Exception | None) -> dict[str, Any]:
    message = str(exc) if exc else "No fue posible extraer condiciones."
    return {
        "nrc": str(nrc),
        "requisitos_aprobacion": None,
        "requisitos_exencion": None,
        "formula_nota_final": None,
        "nota_final_reprobados": None,
        "otros_criterios": None,
        "evidencia_textual": [],
        "confianza_extraccion": 0,
        "advertencias": [f"No fue posible extraer condiciones para el NRC {nrc}: {message}"],
    }


def _clean_formula_field(value: Any) -> str | None:
    text = _normalize_decimal_commas(_clean_nullable_text(value))
    if not text:
        return None

    formula = _extract_formula_sentence(text)
    if _is_placeholder_formula(formula):
        return None
    return formula or None


def _clean_rule_field(value: Any) -> str | None:
    text = _normalize_decimal_commas(_clean_nullable_text(value))
    if not text:
        return None
    return "; ".join(_split_sentences_preserving_decimals(text)) or text


def _extract_formula_sentence(text: str) -> str | None:
    for sentence in _split_sentences_preserving_decimals(text):
        if re.search(r"\bNF\s*=", sentence, flags=re.IGNORECASE):
            return _extract_nf_assignment(sentence) or sentence.strip(" .;")
    for sentence in _split_sentences_preserving_decimals(text):
        lowered = sentence.lower()
        if "=" in sentence and ("nota final" in lowered or "nf" in lowered):
            return sentence.strip(" .;")
    for sentence in _split_sentences_preserving_decimals(text):
        formula = _formula_from_explicit_weighted_text(sentence)
        if formula:
            return formula
        expression = sentence.strip(" .;")
        if _looks_like_weighted_expression(expression):
            return f"NF = {expression}"
    return None


def _extract_nf_assignment(text: str) -> str | None:
    match = re.search(r"\bNF\s*=", text, flags=re.IGNORECASE)
    if not match:
        return None
    return text[match.start():].strip(" .;:")


def _formula_from_explicit_weighted_text(text: str) -> str | None:
    pairs = re.findall(
        r"(\d{1,3}(?:[.,]\d+)?)\s*%\s*(?:de\s+)?([A-Z]{1,6})\b",
        text,
        flags=re.IGNORECASE,
    )
    if len(pairs) < 2:
        pairs = re.findall(
            r"(\d+(?:[.,]\d+)?)\s*(?:por\s+ciento|%)\s*(?:de\s+)?(?:la\s+)?(?:nota\s+)?([A-Z]{1,6})\b",
            text,
            flags=re.IGNORECASE,
        )
    if len(pairs) < 2:
        return None

    components = []
    for percent, label in pairs:
        try:
            weight = float(percent.replace(",", ".")) / 100
        except ValueError:
            return None
        if weight <= 0 or weight > 1:
            return None
        components.append(f"{weight:g}*{label.upper()}")
    return f"NF = {' + '.join(components)}"


def _looks_like_weighted_expression(text: str) -> bool:
    if re.search(r"\bNF\s*=", text, flags=re.IGNORECASE):
        return True
    upper = text.upper()
    has_component = len(set(re.findall(r"\b(?:NP|NE|EX|NCAT|NL|P\d*|C\d*|T\d*)\b", upper))) >= 2
    has_weight = bool(re.search(r"\b0\.\d+\s*\*?\s*[A-Z]", upper) or re.search(r"\b\d{1,3}\s*%\s*(?:DE\s+)?[A-Z]", upper))
    has_operator = any(operator in text for operator in ["+", "*"])
    return has_component and has_weight and has_operator


def _is_placeholder_formula(value: str | None) -> bool:
    if not value:
        return False
    compact = re.sub(r"\s+", "", value).upper()
    return compact in {"NF=0", "NOTAFINAL=0"}


def _split_sentences_preserving_decimals(text: str) -> list[str]:
    text = _clean_nullable_text(text) or ""
    if not text:
        return []

    pieces = re.split(r"\s*(?:[\n•]+|(?<!\d)\.(?!\d))\s*", text)
    return [piece.strip(" ;") for piece in pieces if piece.strip(" ;")]


def _normalize_evidence(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    evidence = []
    for item in value:
        if not isinstance(item, dict):
            continue
        field = _clean_nullable_text(item.get("campo"))
        fragment = _clean_nullable_text(item.get("fragmento"))
        if field and fragment:
            evidence.append({"campo": field, "fragmento": fragment})
    return evidence


def _normalize_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(1, confidence))


def _normalize_decimal_commas(text: str | None) -> str | None:
    if not text:
        return text
    return re.sub(r"(?<=\d),(?=\d)", ".", text)


def _clean_nullable_text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text or text.strip().lower() in {"null", "none", "no especificado", "n/a"}:
        return None
    return text
