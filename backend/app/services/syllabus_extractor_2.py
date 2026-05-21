import re
import pdfplumber
from typing import Any

def extraer_texto_pdf(pdf_path: str) -> str:
    textos = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            textos.append(page.extract_text() or "")

    return "\n".join(textos)

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

        evaluaciones.append({
            "tipo": tipo,
            "ponderacion": parsear_ponderacion(ponderacion),
            "descripcion": descripcion,
        })

    return evaluaciones

def extraer_evaluaciones_y_ponderaciones_pdf(pdf_path: str) -> list[dict[str, Any]]:
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            texto_pagina = page.extract_text() or ""

            if "Evaluaciones y Ponderaciones" not in texto_pagina:
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
                        return evaluaciones

    return []
    
def extraer_texto_seccion_pdf(
    pdf_path: str,
    titulo_seccion: str,
    siguiente_seccion: str | None = None
) -> str:
    textos_paginas = []

    with pdfplumber.open(pdf_path) as pdf:
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

pdf_path = "storage/202610-ING-2106-NRC-7587-TEORIA-DE-PROBABILIDADES (1).pdf"

NRC = pdf_path.split("NRC-")[1].split("-")[0].strip()
print("NRC:", NRC, "\n")
print("Evaluaciones:", extraer_evaluaciones_y_ponderaciones_pdf(pdf_path), "\n")
print("Requisitos de Aprobación:", extraer_texto_seccion_pdf(pdf_path, "Requisitos de Aprobación", "Nota Final de la Asignatura"), "\n")
print("nota final:", extraer_texto_seccion_pdf(pdf_path, "Nota Final de la Asignatura", "Recursos de Aprendizaje - Bibliografía Básica"), "\n")

def main(pdf_path: str):

    
    NRC = pdf_path.split("NRC-")[1].split("-")[0].strip()
    print("NRC:", NRC, "\n")
    print("Evaluaciones:", extraer_evaluaciones_y_ponderaciones_pdf(pdf_path), "\n")
    print("Requisitos de Aprobación:", extraer_texto_seccion_pdf(pdf_path, "Requisitos de Aprobación", "Nota Final de la Asignatura"), "\n")
    print("nota final:", extraer_texto_seccion_pdf(pdf_path, "Nota Final de la Asignatura", "Recursos de Aprendizaje - Bibliografía Básica"), "\n")