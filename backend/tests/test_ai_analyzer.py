from app.services.ai_analyzer import (
    analyze_syllabi_with_ai,
    _combine_section_comparisons,
    _comparison_user_prompt_for_section,
)
from app.services.section_extractor import extract_sections_from_text


class FakeSyllabus:
    def __init__(self, nrc, text):
        self.nrc = nrc
        self.text_content = text
        self.course_code = "2207"
        self.course_name = "TERMODINAMICA"
        self.academic_period = "202610"
        self.year = 2026
        self.term = "10"
        self.career = "ING"
        self.original_filename = f"202610-ING-2207-NRC-{nrc}-TERMODINAMICA.pdf"
        self.extraction_status = "ok"


class FakeAIClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, *, system_prompt, user_prompt, schema_name, schema):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "schema_name": schema_name,
                "schema": schema,
            }
        )
        if schema_name.endswith("_comparison_report"):
            return {
                "analysis_mode": "pairwise",
                "compared_nrcs": ["7542", "7543"],
                "overall_summary": "Se detectó una diferencia en el umbral de eximición.",
                "severity_counts": {"critica": 1, "moderada": 0, "menor": 0},
                "possible_outlier": {"nrc": "", "alert_count": 0, "reason": ""},
                "inconsistencies": [
                    {
                        "section": "Criterios de Eximición",
                        "variable": "Umbral de eximición",
                        "difference": "NRC 7542 exige 5,5 y NRC 7543 exige 5,8.",
                        "involved_nrcs": ["7542", "7543"],
                        "severity": "Crítica",
                        "priority_rationale": "Afecta directamente la eximición del examen.",
                        "suggestion": "Confirmar el umbral oficial y unificar los syllabus.",
                        "evidence": "Extracción estructurada de ambos NRC.",
                        "is_main_alert": True,
                    }
                ],
            }

        return {
            "section_name": "Criterios de Eximición",
            "section_found": True,
            "confidence": 0.9,
            "relevant_excerpt": "Eximición con promedio igual o superior a 5,5.",
            "extracted_variables": [
                {
                    "name": "Umbral de eximición",
                    "value": "5,5",
                    "normalized_value": "5.5",
                    "evidence": "promedio igual o superior a 5,5",
                    "academic_relevance": "Define eximición de examen.",
                }
            ],
            "missing_or_ambiguous_elements": [],
            "academic_interpretation": "Regla explícita de eximición.",
        }


def test_ai_analyzer_uses_section_prompts_and_comparison_prompt(monkeypatch):
    class FakeSettings:
        ai_max_pdf_text_chars = 5000
        local_model = "qwen2.5:14b"

    monkeypatch.setattr("app.services.ai_analyzer.get_settings", lambda: FakeSettings())

    client = FakeAIClient()
    syllabi = [
        FakeSyllabus(
            "7542",
            """
Evaluaciones y Ponderaciones
Pruebas 30
Cronograma de Actividades
Semana 1
Requisitos de Aprobación
Nota mínima 4.0
Criterios de Eximición
Promedio igual o superior a 5,5
Nota Final de la Asignatura
NF = 0.7 NP + 0.3 EX
Recursos de Aprendizaje - Bibliografía Básica
Libro base
""",
        ),
        FakeSyllabus(
            "7543",
            """
Evaluaciones y Ponderaciones
Pruebas 30
Cronograma de Actividades
Semana 1
Requisitos de Aprobación
Nota mínima 4.0
Criterios de Eximición
Promedio igual o superior a 5,8
Nota Final de la Asignatura
NF = 0.7 NP + 0.3 EX
Recursos de Aprendizaje - Bibliografía Básica
Libro base
""",
        ),
    ]

    result = analyze_syllabi_with_ai(
        syllabi,
        {
            "academic_period": "202610",
            "course_code": "2207",
            "course_name": "TERMODINAMICA",
        },
        client=client,
        max_text_chars=5000,
    )

    section_calls = [call for call in client.calls if call["schema_name"].endswith("_extraction")]
    comparison_calls = [
        call for call in client.calls if call["schema_name"].endswith("_comparison_report")
    ]

    assert len(section_calls) == 0
    assert len(comparison_calls) == 4
    assert result["summary"]["analysis_provider"] == "ollama"
    assert result["summary"]["severity_counts"]["Crítica"] == 4
    assert result["inconsistencies"][0]["variable"] == "Umbral de eximición"


def test_comparison_prompt_uses_section_recortes():
    prompt = _comparison_user_prompt_for_section(
        {"academic_period": "202610", "course_code": "2207", "course_name": "TERMODINAMICA"},
        "evaluations",
        "Evaluaciones y Ponderaciones",
        {
            "7542": {
                "metadata": {"nrc": "7542"},
                "sections": {
                    "evaluations": {
                        "section_name": "Evaluaciones y Ponderaciones",
                        "source_excerpt": "Evaluaciones y Ponderaciones\nPruebas | 10 | Prueba 1",
                        "source_strategy": "keyword_window",
                        "extracted_variables": [{"name": "Prueba 1", "value": "10"}],
                        "missing_or_ambiguous_elements": [],
                        "academic_interpretation": "Tabla de evaluaciones",
                    }
                },
            }
        },
    )

    assert "Texto del mismo apartado extraído localmente" in prompt
    assert "Pruebas | 10 | Prueba 1" in prompt
    assert "evaluations" in prompt


def test_equivalent_evaluation_weight_order_is_not_reported_as_alert():
    comparison = {
        "analysis_mode": "pairwise",
        "compared_nrcs": ["7587", "7588"],
        "overall_summary": "Se detectó una diferencia en ponderaciones.",
        "severity_counts": {"critica": 1, "moderada": 0, "menor": 0},
        "possible_outlier": {"nrc": "", "alert_count": 0, "reason": ""},
        "inconsistencies": [
            {
                "section": "Evaluaciones y Ponderaciones",
                "variable": "Ponderación de Pruebas",
                "difference": (
                    "NRC 7587: 30% Examen Final, 52.5% Pruebas "
                    "NRC 7588: 52.5% Pruebas, 30% Examen Final"
                ),
                "involved_nrcs": ["7587", "7588"],
                "severity": "Crítica",
                "priority_rationale": "Afecta evaluación.",
                "suggestion": "Revisar y unificar las ponderaciones.",
                "evidence": "Extracción del apartado.",
                "is_main_alert": True,
            }
        ],
    }

    result = _combine_section_comparisons([comparison], ["7587", "7588"])

    assert result["inconsistencies"] == []
    assert result["severity_counts"] == {"critica": 0, "moderada": 0, "menor": 0}
    assert result["possible_outlier"]["nrc"] == ""
    assert "No se detectaron diferencias relevantes" in result["overall_summary"]


def test_extract_sections_from_text_uses_heading_boundaries():
    text = """
--- Página 1 ---
Información de la Asignatura
Carrera: ING
Información del Instructor
Docente Uno
Evaluaciones y Ponderaciones
Tipo Ponderación
Pruebas 30
Cronograma de Actividades
Semana 1
Requisitos de Aprobación
Nota mínima 4.0
Nota Final de la Asignatura
NF = 0.7 NP + 0.3 EX
Recursos de Aprendizaje - Bibliografía Básica
Libro base
""".strip()

    sections = extract_sections_from_text(text, 5000)

    assert sections["evaluations"]["section_found"] is True
    assert "Pruebas 30" in sections["evaluations"]["source_excerpt"]
    assert "Cronograma de Actividades" not in sections["evaluations"]["source_excerpt"]
    assert sections["final_grade"]["source_strategy"] == "heading_boundaries"


def test_empty_section_returns_placeholder_result(monkeypatch):
    from app.services.ai_analyzer import _extract_section_result

    class EmptySyllabus(FakeSyllabus):
        def __init__(self):
            super().__init__("7542", "")

    class NeverCalledClient:
        def complete_json(self, **kwargs):
            raise AssertionError("The model should not be called for empty sections")

    result = _extract_section_result(
        NeverCalledClient(),
        EmptySyllabus(),
        type("SectionPromptLike", (), {"key": "evaluations", "name": "Evaluaciones y Ponderaciones"})(),
        1000,
    )

    assert result["section_found"] is False
    assert result["source_strategy"] == "missing"
    assert result["extracted_variables"] == []
