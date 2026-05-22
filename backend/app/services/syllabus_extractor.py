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
SECTION_CRONOGRAMA = "Cronograma de Actividades"

NEXT_SECTIONS_AFTER_EVALUACIONES = [
    SECTION_CRONOGRAMA,
    SECTION_REQUISITOS,
    SECTION_EXIMICION,
    SECTION_NOTA_FINAL,
    SECTION_BIBLIOGRAFIA,
]


def _abrir_pdf(pdf_path: str):
    if pdfplumber is None:
        raise RuntimeError("pdfplumber no está instalado; no se puede ejecutar la extracción estructurada.")
    return pdfplumber.open(pdf_path)


def extraer_texto_pdf(pdf_path: str, *, layout: bool = False) -> str:
    textos = []

    with _abrir_pdf(pdf_path) as pdf:
        for page in pdf.pages:
            textos.append(page.extract_text(layout=layout) or "")

    return "\n".join(textos)


def _rango_seccion_en_texto(
    texto_completo: str,
    titulo_seccion: str,
    siguientes_secciones: str | list[str] | None = None,
) -> tuple[int, int] | None:
    start_title = texto_completo.find(titulo_seccion)
    if start_title == -1:
        return None

    start = start_title + len(titulo_seccion)
    siguientes = []
    if isinstance(siguientes_secciones, str):
        siguientes = [siguientes_secciones]
    elif siguientes_secciones:
        siguientes = siguientes_secciones

    end_candidates = [
        index
        for siguiente in siguientes
        if (index := texto_completo.find(siguiente, start)) != -1
    ]
    end = min(end_candidates) if end_candidates else len(texto_completo)
    return start, end


def _paginas_en_rango_seccion(
    textos_paginas: list[tuple[int, str]],
    titulo_seccion: str,
    siguientes_secciones: str | list[str] | None = None,
) -> list[int]:
    texto_completo = "\n".join(texto for _, texto in textos_paginas)
    rango = _rango_seccion_en_texto(texto_completo, titulo_seccion, siguientes_secciones)
    if rango is None:
        return []

    section_start, section_end = rango
    page_spans: list[tuple[int, int, int]] = []
    cursor = 0
    for page_num, page_text in textos_paginas:
        page_start = cursor
        page_end = page_start + len(page_text)
        page_spans.append((page_num, page_start, page_end))
        cursor = page_end + 1

    return [
        page_num
        for page_num, page_start, page_end in page_spans
        if page_end >= section_start and page_start < section_end
    ]


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
    texto = re.sub(r"\bPage\s+\d+\s+of\s+\d+\b", " ", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s+", " ", texto)

    return texto if texto else None


def _texto_tabla_evaluaciones(texto: str) -> str:
    header_match = re.search(
        r"Tipo\s+de\s+Evaluaci[oó]n\s+Ponderaci[oó]n\s*\(%\)\s+Descripci[oó]n",
        texto,
        re.IGNORECASE,
    )
    if not header_match:
        return texto

    texto_tabla = texto[header_match.end():]
    cronograma_index = texto_tabla.find(SECTION_CRONOGRAMA)
    if cronograma_index != -1:
        texto_tabla = texto_tabla[:cronograma_index]
    return texto_tabla.strip()


def _lineas_evaluaciones(texto: str) -> list[str]:
    return [
        linea_limpia
        for linea in texto.splitlines()
        if (linea_limpia := limpiar_texto(linea))
        and not re.fullmatch(r"Page\s+\d+\s+of\s+\d+", linea_limpia, re.IGNORECASE)
    ]


def _termina_frase(texto: str) -> bool:
    return texto.rstrip().endswith((".", ";", ":"))


def _normalizar_celda(valor: Any) -> str | None:
    return limpiar_texto(valor)


def _indice_columna(row: list[Any], patrones: list[str]) -> int | None:
    for index, cell in enumerate(row):
        text = _normalizar_celda(cell) or ""
        text = text.lower()
        if all(patron in text for patron in patrones):
            return index
    return None


def _parsear_evaluaciones_desde_filas_tabla(rows: list[list[Any]]) -> list[dict[str, Any]]:
    evaluaciones: list[dict[str, Any]] = []
    tipo_index: int | None = None
    ponderacion_index: int | None = None
    descripcion_index: int | None = None
    in_evaluaciones = False

    for row in rows:
        normalized_row = [_normalizar_celda(cell) for cell in row]
        row_text = " ".join(cell for cell in normalized_row if cell)

        if SECTION_EVALUACIONES.lower() in row_text.lower():
            in_evaluaciones = True
            continue

        if in_evaluaciones and any(section.lower() in row_text.lower() for section in NEXT_SECTIONS_AFTER_EVALUACIONES):
            break

        current_tipo_index = _indice_columna(row, ["tipo", "evaluaci"])
        current_ponderacion_index = _indice_columna(row, ["ponder"])
        current_descripcion_index = _indice_columna(row, ["descrip"])
        if (
            current_tipo_index is not None
            and current_ponderacion_index is not None
            and current_descripcion_index is not None
        ):
            tipo_index = current_tipo_index
            ponderacion_index = current_ponderacion_index
            descripcion_index = current_descripcion_index
            in_evaluaciones = True
            continue

        if not in_evaluaciones or tipo_index is None or ponderacion_index is None or descripcion_index is None:
            continue

        tipo = normalized_row[tipo_index] if tipo_index < len(normalized_row) else None
        ponderacion = normalized_row[ponderacion_index] if ponderacion_index < len(normalized_row) else None
        descripcion = normalized_row[descripcion_index] if descripcion_index < len(normalized_row) else None

        if not tipo or parsear_ponderacion(ponderacion or "") is None:
            continue

        evaluaciones.append(
            {
                "tipo": tipo,
                "ponderacion": parsear_ponderacion(ponderacion),
                "descripcion": descripcion,
            }
        )

    return evaluaciones


def _extraer_evaluaciones_desde_tablas_pdf(pdf: Any, paginas_seccion: list[int]) -> list[dict[str, Any]]:
    for page_num in paginas_seccion:
        page = pdf.pages[page_num - 1]
        for table in page.find_tables():
            evaluaciones = _parsear_evaluaciones_desde_filas_tabla(table.extract())
            if evaluaciones:
                return evaluaciones

    return []


def _parsear_evaluaciones_desde_texto(texto: str) -> list[dict[str, Any]]:
    texto_tabla = _texto_tabla_evaluaciones(texto)
    if not texto_tabla:
        return []

    tipos = [
        "Pruebas",
        "Controles",
        "Talleres",
        "Laboratorios",
        "Otros",
        "Examen",
        "Tareas",
        "Trabajos",
        "Proyecto",
        "Presentaciones",
    ]
    tipo_pattern = "|".join(re.escape(tipo) for tipo in tipos)
    row_pattern = re.compile(
        rf"^\s*(?P<tipo>{tipo_pattern})\b\s+(?P<ponderacion>\d+(?:[.,]\d+)?\s*%?)\b(?P<resto>.*)$",
        re.IGNORECASE,
    )
    lineas = _lineas_evaluaciones(texto_tabla)
    rows = [
        (index, match)
        for index, linea in enumerate(lineas)
        if (match := row_pattern.match(linea))
    ]
    if not rows:
        return []

    descripciones: list[list[str]] = [[] for _ in rows]
    evaluaciones = [
        {
            "tipo": match.group("tipo"),
            "ponderacion": parsear_ponderacion(match.group("ponderacion")),
            "descripcion": None,
        }
        for _, match in rows
    ]

    for row_pos, (line_index, match) in enumerate(rows):
        if row_pos == 0:
            descripciones[row_pos].extend(lineas[:line_index])
        else:
            previous_line_index = rows[row_pos - 1][0]
            intermedias = lineas[previous_line_index + 1:line_index]
            if len(intermedias) >= 2 and _termina_frase(intermedias[0]):
                descripciones[row_pos - 1].append(intermedias[0])
                descripciones[row_pos].extend(intermedias[1:])
            else:
                descripciones[row_pos - 1].extend(intermedias)

        resto = limpiar_texto(match.group("resto"))
        if resto:
            descripciones[row_pos].append(resto)

    last_row_index = rows[-1][0]
    descripciones[-1].extend(lineas[last_row_index + 1:])

    for index, partes in enumerate(descripciones):
        evaluaciones[index]["descripcion"] = limpiar_texto(" ".join(partes))

    return evaluaciones


def extraer_evaluaciones_y_ponderaciones_con_pagina_pdf(pdf_path: str) -> tuple[list[dict[str, Any]], list[int], str | None]:
    with _abrir_pdf(pdf_path) as pdf:
        textos_paginas = [
            (page_num, page.extract_text() or "")
            for page_num, page in enumerate(pdf.pages, start=1)
        ]
        paginas_seccion = _paginas_en_rango_seccion(
            textos_paginas,
            SECTION_EVALUACIONES,
            NEXT_SECTIONS_AFTER_EVALUACIONES,
        )
        if not paginas_seccion:
            return [], [], None

        evaluaciones = _extraer_evaluaciones_desde_tablas_pdf(pdf, paginas_seccion)
        if evaluaciones:
            return evaluaciones, paginas_seccion, " | ".join(
                f"{item['tipo']}: {item['ponderacion']}% ({item['descripcion'] or 'sin descripción'})"
                for item in evaluaciones
            )

    texto = extraer_texto_seccion_pdf(
        pdf_path,
        SECTION_EVALUACIONES,
        NEXT_SECTIONS_AFTER_EVALUACIONES,
        layout=True,
    )
    evaluaciones = _parsear_evaluaciones_desde_texto(texto)
    if evaluaciones:
        return evaluaciones, paginas_seccion, " | ".join(
            f"{item['tipo']}: {item['ponderacion']}% ({item['descripcion'] or 'sin descripción'})"
            for item in evaluaciones
        )

    return [], [], None


def extraer_evaluaciones_y_ponderaciones_pdf(pdf_path: str) -> list[dict[str, Any]]:
    evaluaciones, _, _ = extraer_evaluaciones_y_ponderaciones_con_pagina_pdf(pdf_path)
    return evaluaciones


def extraer_texto_seccion_pdf(
    pdf_path: str,
    titulo_seccion: str,
    siguiente_seccion: str | list[str] | None = None,
    *,
    layout: bool = False,
) -> str:
    textos_paginas = []

    with _abrir_pdf(pdf_path) as pdf:
        for page in pdf.pages:
            texto = page.extract_text(layout=layout) or ""
            textos_paginas.append(texto)

    texto_completo = "\n".join(textos_paginas)
    rango = _rango_seccion_en_texto(texto_completo, titulo_seccion, siguiente_seccion)
    if rango is None:
        return ""

    start, end = rango
    texto = texto_completo[start:end].strip()

    if layout:
        return texto.strip()

    return limpiar_texto(texto) or ""


def extraer_texto_seccion_con_paginas_pdf(
    pdf_path: str,
    titulo_seccion: str,
    siguiente_seccion: str | None = None,
) -> tuple[str, list[int]]:
    textos_paginas: list[tuple[int, str]] = []

    with _abrir_pdf(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            textos_paginas.append((page_num, page.extract_text() or ""))

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


def generar_json_syllabus(pdf_path: str) -> dict[str, Any]:
    requisitos_texto = extraer_texto_seccion_pdf(pdf_path, SECTION_REQUISITOS, SECTION_NOTA_FINAL)
    eximicion_texto = extraer_texto_seccion_pdf(pdf_path, SECTION_EXIMICION, SECTION_NOTA_FINAL)
    nota_final_texto = extraer_texto_seccion_pdf(pdf_path, SECTION_NOTA_FINAL, SECTION_BIBLIOGRAFIA)

    return {
        "nrc": extraer_nrc_desde_ruta(pdf_path),
        "evaluaciones": extraer_evaluaciones_y_ponderaciones_pdf(pdf_path),
        "requisitos_aprobacion": requisitos_texto,
        "criterios_eximicion": eximicion_texto,
        "nota_final": nota_final_texto,
    }


def extract_normalized_syllabus_json_from_pdf(syllabus: Any) -> dict[str, Any]:
    pdf_path = str(syllabus.stored_path)
    nrc = str(getattr(syllabus, "nrc", "") or "").strip() or extraer_nrc_desde_ruta(pdf_path)
    result = generar_json_syllabus(pdf_path)
    result["nrc"] = nrc
    return result
