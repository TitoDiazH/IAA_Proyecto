from app.services.pdf_extractor import clean_pdf_text


def test_clean_pdf_text_collapses_noise_and_keeps_line_breaks():
    raw = "Línea 1\r\n\r\n\r\nLínea 2   con   espacios\r\nFinal"

    cleaned = clean_pdf_text(raw)

    assert "\r" not in cleaned
    assert "  " not in cleaned
    assert "Línea 1" in cleaned
    assert "Línea 2 con espacios" in cleaned
