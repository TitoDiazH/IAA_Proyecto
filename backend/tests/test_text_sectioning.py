from app.services.ai_analyzer import _section_prompt_text
from app.services.pdf_extractor import clean_pdf_text


def test_clean_pdf_text_collapses_noise_and_keeps_line_breaks():
    raw = "Línea 1\r\n\r\n\r\nLínea 2   con   espacios\r\nFinal"

    cleaned = clean_pdf_text(raw)

    assert "\r" not in cleaned
    assert "  " not in cleaned
    assert "Línea 1" in cleaned
    assert "Línea 2 con espacios" in cleaned


def test_section_prompt_text_focuses_general_info_and_keywords():
    text = """
--- Página 1 ---
Información general de la asignatura
Nombre asignatura: Mecánica y Ondas
Créditos: 6
Modalidad: Presencial

--- Página 2 ---
Descripción del curso

--- Página 7 ---
Evaluaciones y Ponderaciones
Pruebas | 10 | Prueba 1
Controles | 15 | 6 Controles (se elimina 1)
""".strip()

    general_info = _section_prompt_text(text, "general_info", 1000)
    evaluations = _section_prompt_text(text, "evaluations", 1000)

    assert "Nombre asignatura" in general_info
    assert "Créditos: 6" in general_info
    assert "Evaluaciones y Ponderaciones" not in general_info
    assert "Evaluaciones y Ponderaciones" in evaluations
    assert "Pruebas | 10 | Prueba 1" in evaluations
