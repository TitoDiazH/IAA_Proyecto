from app.services import syllabus_extractor


class FakePage:
    def __init__(self, text, tables=None):
        self.text = text
        self.tables = tables or []

    def extract_text(self, layout=False):
        return self.text

    def extract_tables(self):
        return self.tables


class FakePdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_extracts_evaluations_from_text_between_sections_across_pages(monkeypatch):
    fake_pdf = FakePdf(
        [
            FakePage("Evaluaciones y Ponderaciones\nTexto introductorio sin tabla."),
            FakePage(
                "Tipo de Evaluación Ponderación (%) Descripción\n"
                "Pruebas escritas\n"
                "Pruebas 50\n"
                "Primera parte.\n"
                "Examen final\n"
                "Examen 50\n"
                "Segunda parte."
            ),
            FakePage("Requisitos de Aprobación\nPara aprobar se requiere NF >= 4.0."),
        ]
    )
    monkeypatch.setattr(syllabus_extractor, "_abrir_pdf", lambda pdf_path: fake_pdf)

    evaluaciones, pages, evidence = syllabus_extractor.extraer_evaluaciones_y_ponderaciones_con_pagina_pdf("fake.pdf")

    assert pages == [1, 2]
    assert evaluaciones == [
        {"tipo": "Pruebas", "ponderacion": 50.0, "descripcion": "Pruebas escritas Primera parte."},
        {"tipo": "Examen", "ponderacion": 50.0, "descripcion": "Examen final Segunda parte."},
    ]
    assert "Pruebas: 50.0%" in evidence


def test_extracts_text_between_sections_across_pages(monkeypatch):
    fake_pdf = FakePdf(
        [
            FakePage("Requisitos de Aprobación\nPrimera parte."),
            FakePage("Segunda parte de los requisitos."),
            FakePage("Nota Final de la Asignatura\nNF = 0.5 P + 0.5 EX"),
        ]
    )
    monkeypatch.setattr(syllabus_extractor, "_abrir_pdf", lambda pdf_path: fake_pdf)

    text = syllabus_extractor.extraer_texto_seccion_pdf(
        "fake.pdf",
        syllabus_extractor.SECTION_REQUISITOS,
        syllabus_extractor.SECTION_NOTA_FINAL,
    )

    assert text == "Primera parte. Segunda parte de los requisitos."
