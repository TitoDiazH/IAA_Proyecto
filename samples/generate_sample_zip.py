from __future__ import annotations

import sys
import textwrap
import zipfile
from pathlib import Path


def escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf_bytes(text: str) -> bytes:
    """Create a tiny text PDF without external dependencies.

    The generated PDFs are intentionally simple so pypdf can extract their text
    during local demos.
    """

    lines = []
    for raw_line in textwrap.dedent(text).strip().splitlines():
        line = raw_line.strip()
        if line:
            lines.append(line)

    stream_lines = ["BT", "/F1 11 Tf", "14 TL", "50 750 Td"]
    for index, line in enumerate(lines):
        if index:
            stream_lines.append("T*")
        stream_lines.append(f"({escape_pdf_text(line)}) Tj")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            "trailer\n"
            f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            "startxref\n"
            f"{xref_offset}\n"
            "%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


SAMPLES = {
    "202610-ING-2207-NRC-7542-TERMODINAMICA.pdf": """
        Evaluaciones y Ponderaciones
        Prueba 1: 30%
        Trabajo: 20%
        Examen: 50%
        Requisitos de Aprobación
        Para aprobar se requiere nota final igual o superior a 4,0.
        Para rendir examen se requiere promedio igual o superior a 3,5.
        Criterios de Eximición
        El estudiante podrá eximirse con promedio igual o superior a 5,5.
        Nota Final de la Asignatura
        NF = Prueba 1 30% + Trabajo 20% + Examen 50%.
    """,
    "202610-ING-2207-NRC-7543-TERMODINAMICA.pdf": """
        Evaluaciones y Ponderaciones
        Prueba 1: 30%
        Trabajo: 20%
        Examen: 50%
        Requisitos de Aprobación
        La asignatura se aprueba con nota final igual o mayor a 4,0.
        Quienes tengan promedio igual o superior a 3,5 podrán rendir examen.
        Criterios de Eximición
        Quienes obtengan nota final previa igual o mayor a 5,5 estarán eximidos del examen.
        Nota Final de la Asignatura
        NF = Prueba 1 30% + Trabajo 20% + Examen 50%.
    """,
    "202610-ING-2207-NRC-7544-TERMODINAMICA.pdf": """
        Evaluaciones y Ponderaciones
        Prueba 1: 25%
        Trabajo: 25%
        Examen: 50%
        Requisitos de Aprobación
        Para aprobar se requiere nota final igual o superior a 4,0.
        Para rendir examen se requiere promedio igual o superior a 3,5.
        Criterios de Eximición
        El estudiante podrá eximirse con promedio igual o superior a 5,8.
        Nota Final de la Asignatura
        NF = Prueba 1 25% + Trabajo 25% + Examen 50%.
    """,
}


def main() -> None:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "samples/syllabus_demo.zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, text in SAMPLES.items():
            archive.writestr(filename, make_pdf_bytes(text))
    print(f"ZIP de ejemplo generado en {output}")


if __name__ == "__main__":
    main()

