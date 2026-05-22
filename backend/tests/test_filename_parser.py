import pytest

from app.services.filename_parser import FilenameParseError, parse_syllabus_filename


def test_parse_expected_filename():
    parsed = parse_syllabus_filename("202610-ING-2207-NRC-7542-TERMODINAMICA.pdf")

    assert parsed.year == 2026
    assert parsed.term == "10"
    assert parsed.career == "ING"
    assert parsed.course_code == "ING2207"
    assert parsed.nrc == "7542"
    assert parsed.course_name == "Termodinamica"


def test_parse_course_name_without_hyphens():
    parsed = parse_syllabus_filename("202610-ING-2105-NRC-7942-MECANICA-Y-ONDAS.pdf")

    assert parsed.course_name == "Mecanica y Ondas"


def test_reject_non_pdf():
    with pytest.raises(FilenameParseError):
        parse_syllabus_filename("202610-ING-2207-NRC-7542-TERMODINAMICA.docx")
