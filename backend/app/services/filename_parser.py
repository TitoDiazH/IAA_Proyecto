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


LOWERCASE_COURSE_WORDS = {
    "a",
    "al",
    "de",
    "del",
    "e",
    "el",
    "en",
    "la",
    "las",
    "los",
    "o",
    "u",
    "y",
}
ROMAN_NUMERALS = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}


def normalize_course_name(course_name: str | None) -> str:
    clean_name = re.sub(r"[-_]+", " ", course_name or "")
    clean_name = re.sub(r"\s+", " ", clean_name).strip()

    words = []
    for index, word in enumerate(clean_name.split(" ")):
        upper_word = word.upper()
        lower_word = word.lower()

        if index > 0 and lower_word in LOWERCASE_COURSE_WORDS:
            words.append(lower_word)
        elif upper_word in ROMAN_NUMERALS or (word.isupper() and len(word) <= 3):
            words.append(upper_word)
        else:
            words.append(word[:1].upper() + word[1:].lower())

    return " ".join(words)


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

    career_code = career.strip().upper()
    base_course_code = course_code.strip().upper()

    return ParsedSyllabusFilename(
        academic_period=academic_period,
        year=int(academic_period[:4]),
        term=academic_period[4:],
        career=career_code,
        course_code=f"{career_code}{base_course_code}",
        nrc=nrc_number.strip(),
        course_name=normalize_course_name(course_name),
    )


def slugify_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFKD", Path(filename).name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name)
    return ascii_name.strip("._") or "syllabus.pdf"
