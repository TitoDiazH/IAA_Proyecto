import re
from typing import Any

try:
    import pdfplumber
except ImportError:  # pragma: no cover - allows importing this module in minimal test envs
    pdfplumber = None


SECTION_EVALUACIONES = "Evaluaciones y Ponderaciones"
SECTION_REQUISITOS = "Requisitos de Aprobación"
SECTION_EXIMICION = "Criterios de Eximición"
SECTION_NOTA_FINAL = "Nota Final de la Asignatura"
SECTION_BIBLIOGRAFIA = "Recursos de Aprendizaje - Bibliografía Básica"


def _abrir_pdf(pdf_path: str):
    if pdfplumber is None:
        raise RuntimeError("pdfplumber no está instalado; no se puede ejecutar la extracción estructurada.")
    return pdfplumber.open(pdf_path)

def es_ponderacion(valor: str) -> bool:
    if valor is None:
        return False

    valor = str(valor).strip()
    return bool(re.fullmatch(r"\d+(?:[.,]\d+)?\s*%?", valor))


def parsear_ponderacion(valor: str) -> float | None:
    if valor is None:
        return None

    valor = str(valor).strip().replace("%", "").replace(",", ".")

    try:
        return float(valor)
    except ValueError:
        return None


def limpiar_texto(valor: Any) -> str | None:
    if valor is None:
        return None

    texto = str(valor).replace("\n", " ").strip()
    texto = re.sub(r"\s+", " ", texto)

    return texto if texto else None


def fila_es_encabezado(row: list[Any]) -> bool:
    texto = " ".join(str(c or "") for c in row).lower()

    return (
        "tipo" in texto
        and "ponder" in texto
        and "descrip" in texto
    )


def extraer_cantidad_evaluaciones(tipo: str | None, descripcion: str | None) -> int | None:
    texto = " ".join(filter(None, [tipo, descripcion]))
    match = re.search(r"\b(\d+)\s*(?:evaluaciones?|pruebas?|controles?|tareas?|trabajos?)\b", texto, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def normalizar_tabla_evaluaciones(table: list[list[Any]]) -> list[dict[str, Any]]:
    evaluaciones = []

    for row in table:
        if not row:
            continue

        row = [limpiar_texto(cell) for cell in row]

        if fila_es_encabezado(row):
            continue

        # Nos aseguramos de tener al menos 3 columnas
        if len(row) < 3:
            continue

        tipo = row[0]
        ponderacion = row[1]
        descripcion = row[2]

        if not tipo or not es_ponderacion(ponderacion):
            continue

        weight_total = parsear_ponderacion(ponderacion)
        quantity = extraer_cantidad_evaluaciones(tipo, descripcion)

        evaluaciones.append(
            {
                "type": tipo,
                "quantity": quantity,
                "weight_total": weight_total,
                "weight_each": round(weight_total / quantity, 2) if weight_total is not None and quantity else None,
                "description": descripcion,
            }
        )

    return evaluaciones


def extraer_evaluaciones_y_ponderaciones_con_pagina_pdf(pdf_path: str) -> tuple[list[dict[str, Any]], list[int], str | None]:
    with _abrir_pdf(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            texto_pagina = page.extract_text() or ""

            if SECTION_EVALUACIONES not in texto_pagina:
                continue

            tables = page.extract_tables()

            for table in tables:
                if not table:
                    continue

                table_text = " ".join(
                    str(cell or "")
                    for row in table
                    for cell in row
                ).lower()

                if (
                    "tipo" in table_text
                    and "ponder" in table_text
                    and "descrip" in table_text
                ):
                    evaluaciones = normalizar_tabla_evaluaciones(table)

                    if evaluaciones:
                        return evaluaciones, [page_num], " | ".join(
                            f"{item['type']}: {item['weight_total']}% ({item['description'] or 'sin descripción'})"
                            for item in evaluaciones
                        )

    return [], [], None


def extraer_texto_seccion_pdf(
    pdf_path: str,
    titulo_seccion: str,
    siguiente_seccion: str | None = None
) -> str:
    textos_paginas = []

    with _abrir_pdf(pdf_path) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            textos_paginas.append(texto)

    texto_completo = "\n".join(textos_paginas)

    if titulo_seccion not in texto_completo:
        return ""

    start = texto_completo.index(titulo_seccion) + len(titulo_seccion)

    if siguiente_seccion and siguiente_seccion in texto_completo[start:]:
        end = texto_completo.index(siguiente_seccion, start)
    else:
        end = len(texto_completo)

    texto = texto_completo[start:end].strip()

    # Pasar a texto continuo
    texto = re.sub(r"\s*\n+\s*", " ", texto)
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


def extraer_texto_seccion_con_paginas_pdf(
    pdf_path: str,
    titulo_seccion: str,
    siguiente_seccion: str | None = None,
) -> tuple[str, list[int]]:
    textos_paginas: list[tuple[int, str]] = []

    with _abrir_pdf(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            textos_paginas.append((page_num, page.extract_text() or ""))

    texto_completo = "\n".join(texto for _, texto in textos_paginas)
    texto = extraer_texto_seccion_pdf(pdf_path, titulo_seccion, siguiente_seccion)
    if not texto:
        return "", []

    page_numbers = [
        page_num
        for page_num, page_text in textos_paginas
        if titulo_seccion in page_text or texto[:80] in re.sub(r"\s+", " ", page_text)
    ]
    return texto, sorted(set(page_numbers))


def extraer_nrc_desde_ruta(pdf_path: str) -> str:
    match = re.search(r"NRC-([^-]+)", pdf_path)
    return match.group(1).strip() if match else ""


def _section_payload(
    *,
    found: bool,
    page_numbers: list[int] | None = None,
    raw_evidence: str | None = None,
    structured_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not found:
        return {"found": False, "page_numbers": [], "raw_evidence": None, "structured_data": None}

    return {
        "found": True,
        "page_numbers": page_numbers or [],
        "raw_evidence": raw_evidence,
        "structured_data": structured_data,
    }


def _evidencia_breve(texto: str, max_chars: int = 500) -> str | None:
    texto_limpio = limpiar_texto(texto)
    if not texto_limpio:
        return None
    if len(texto_limpio) <= max_chars:
        return texto_limpio
    return texto_limpio[:max_chars].rsplit(" ", 1)[0].strip() + "..."


def _notas_en_texto(texto: str) -> list[float]:
    notas = []
    for match in re.finditer(r"\b([1-7](?:[.,]\d)?)\b", texto):
        nota = parsear_ponderacion(match.group(1))
        if nota is not None:
            notas.append(nota)
    return notas


def _extraer_nota_por_contexto(texto: str, patrones: list[str]) -> float | None:
    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE | re.DOTALL)
        if match:
            notas = _notas_en_texto(match.group(0))
            if notas:
                return notas[0]
    return None


def _extraer_frases_por_palabras(texto: str, palabras: list[str]) -> list[str]:
    frases = []
    for frase in re.split(r"(?<=[.;:])\s+", texto):
        frase_limpia = limpiar_texto(frase)
        if not frase_limpia:
            continue
        frase_normalizada = frase_limpia.lower()
        if any(palabra in frase_normalizada for palabra in palabras):
            frases.append(frase_limpia)
    return frases


def _estructurar_requisitos_aprobacion(texto: str) -> dict[str, Any]:
    return {
        "minimum_final_grade": _extraer_nota_por_contexto(
            texto,
            [
                r"nota\s+m[ií]nima\s+(?:de\s+)?aprobaci[oó]n.{0,80}",
                r"aprobar.{0,80}(?:nota|calificaci[oó]n).{0,30}",
                r"nota\s+final.{0,80}(?:4[,.]0|cuatro)",
            ],
        ),
        "minimum_exam_grade": _extraer_nota_por_contexto(
            texto,
            [
                r"nota\s+m[ií]nima.{0,60}examen.{0,80}",
                r"examen.{0,80}nota\s+m[ií]nima.{0,80}",
                r"examen.{0,80}(?:3[,.]0|3[,.]5|4[,.]0)",
            ],
        ),
        "automatic_failure_rules": _extraer_frases_por_palabras(
            texto,
            ["reprob", "reprueba", "reprobar", "automática", "automatica"],
        ),
        "grade_cap_rules": _extraer_frases_por_palabras(
            texto,
            ["tope", "máxima", "maxima", "nota máxima", "nota maxima"],
        ),
        "attendance_rules": _extraer_frases_por_palabras(texto, ["asistencia"]),
    }


def _estructurar_criterios_eximicion(texto: str) -> dict[str, Any]:
    texto_normalizado = texto.lower()
    is_available = None
    if texto:
        is_available = not any(palabra in texto_normalizado for palabra in ["no existe exim", "no contempla exim", "sin exim"])

    return {
        "is_available": is_available,
        "threshold": _extraer_nota_por_contexto(
            texto,
            [
                r"exim.{0,120}",
                r"promedio.{0,80}(?:igual|superior|mayor).{0,40}",
            ],
        ),
        "conditions": _extraer_frases_por_palabras(
            texto,
            ["exim", "promedio", "igual", "superior", "mayor", "sin notas", "reprob"],
        ),
    }


def _estructurar_nota_final(texto: str) -> dict[str, Any]:
    formula_match = re.search(r"\bNF\s*=\s*[^\s;,]+", texto, re.IGNORECASE)
    presentation_match = re.search(r"\bNP\s*=\s*[^\s;,]+", texto, re.IGNORECASE)
    porcentajes = [parsear_ponderacion(match.group(1)) for match in re.finditer(r"(\d+(?:[.,]\d+)?)\s*%", texto)]
    porcentajes = [valor for valor in porcentajes if valor is not None]

    return {
        "presentation_grade_formula": limpiar_texto(presentation_match.group(0)) if presentation_match else None,
        "final_grade_formula": limpiar_texto(formula_match.group(0)) if formula_match else limpiar_texto(texto),
        "presentation_weight": porcentajes[0] if porcentajes else None,
        "exam_weight": porcentajes[1] if len(porcentajes) > 1 else None,
        "automatic_failure_rules": _extraer_frases_por_palabras(
            texto,
            ["reprob", "reprueba", "reprobar", "automática", "automatica"],
        ),
        "grade_cap_rules": _extraer_frases_por_palabras(
            texto,
            ["tope", "máxima", "maxima", "nota máxima", "nota maxima", "reemplaz"],
        ),
    }


def extract_normalized_syllabus_json_from_pdf(syllabus: Any) -> dict[str, Any]:
    pdf_path = str(syllabus.stored_path)
    warnings: list[str] = []

    evaluaciones, evaluaciones_pages, evaluaciones_evidence = extraer_evaluaciones_y_ponderaciones_con_pagina_pdf(pdf_path)
    requisitos_texto, requisitos_pages = extraer_texto_seccion_con_paginas_pdf(pdf_path, SECTION_REQUISITOS, SECTION_NOTA_FINAL)
    eximicion_texto, eximicion_pages = extraer_texto_seccion_con_paginas_pdf(pdf_path, SECTION_EXIMICION, SECTION_NOTA_FINAL)
    nota_final_texto, nota_final_pages = extraer_texto_seccion_con_paginas_pdf(pdf_path, SECTION_NOTA_FINAL, SECTION_BIBLIOGRAFIA)

    if not evaluaciones:
        warnings.append(f"No se encontraron evaluaciones y ponderaciones para NRC {syllabus.nrc}.")
    if not requisitos_texto:
        warnings.append(f"No se encontró la sección de requisitos de aprobación para NRC {syllabus.nrc}.")
    if not eximicion_texto:
        warnings.append(f"No se encontró la sección de criterios de eximición para NRC {syllabus.nrc}.")
    if not nota_final_texto:
        warnings.append(f"No se encontró la sección de nota final para NRC {syllabus.nrc}.")

    return {
        "metadata": {
            "course_code": syllabus.course_code,
            "course_name": syllabus.course_name,
            "nrc": syllabus.nrc,
            "semester": syllabus.academic_period,
            "academic_period": syllabus.academic_period,
            "source_file": syllabus.original_filename,
        },
        "sections": {
            "evaluaciones_y_ponderaciones": _section_payload(
                found=bool(evaluaciones),
                page_numbers=evaluaciones_pages,
                raw_evidence=evaluaciones_evidence,
                structured_data={"evaluations": evaluaciones} if evaluaciones else None,
            ),
            "requisitos_aprobacion": _section_payload(
                found=bool(requisitos_texto),
                page_numbers=requisitos_pages,
                raw_evidence=_evidencia_breve(requisitos_texto),
                structured_data=_estructurar_requisitos_aprobacion(requisitos_texto) if requisitos_texto else None,
            ),
            "criterios_eximicion": _section_payload(
                found=bool(eximicion_texto),
                page_numbers=eximicion_pages,
                raw_evidence=_evidencia_breve(eximicion_texto),
                structured_data=_estructurar_criterios_eximicion(eximicion_texto) if eximicion_texto else None,
            ),
            "nota_final": _section_payload(
                found=bool(nota_final_texto),
                page_numbers=nota_final_pages,
                raw_evidence=_evidencia_breve(nota_final_texto),
                structured_data=_estructurar_nota_final(nota_final_texto) if nota_final_texto else None,
            ),
        },
        "warnings": warnings,
    }
