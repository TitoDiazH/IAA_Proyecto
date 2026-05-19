from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata


class FilenameParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedSyllabusFilename:
    academic_period: str
    year: int
    term: str
    career: str
    course_code: str
    nrc: str
    course_name: str


def parse_syllabus_filename(filename: str) -> ParsedSyllabusFilename:
    """Parse AÑOSEMESTRE-CARRERA-CODIGOCURSO-NRC-NUMERONRC-NOMBRERAMO.pdf."""

    clean_name = Path(filename).name
    if Path(clean_name).suffix.lower() != ".pdf":
        raise FilenameParseError("El archivo no tiene extensión PDF")

    stem = Path(clean_name).stem
    parts = stem.split("-")
    if len(parts) < 6:
        raise FilenameParseError(
            "El nombre debe seguir AÑOSEMESTRE-CARRERA-CODIGOCURSO-NRC-NUMERONRC-NOMBRERAMO.pdf"
        )

    academic_period, career, course_code, nrc_label, nrc_number = parts[:5]
    course_name = "-".join(parts[5:]).strip()

    if not re.fullmatch(r"\d{6}", academic_period):
        raise FilenameParseError("AÑOSEMESTRE debe tener 6 dígitos, por ejemplo 202610")

    if nrc_label.upper() != "NRC":
        raise FilenameParseError("El cuarto segmento del nombre debe ser NRC")

    if not nrc_number:
        raise FilenameParseError("El número NRC no puede estar vacío")

    if not career or not course_code or not course_name:
        raise FilenameParseError("Carrera, código de curso y nombre de ramo son obligatorios")

    return ParsedSyllabusFilename(
        academic_period=academic_period,
        year=int(academic_period[:4]),
        term=academic_period[4:],
        career=career.strip().upper(),
        course_code=course_code.strip().upper(),
        nrc=nrc_number.strip(),
        course_name=course_name.replace("_", " ").strip().upper(),
    )


def slugify_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFKD", Path(filename).name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name)
    return ascii_name.strip("._") or "syllabus.pdf"

