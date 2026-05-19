from app.services.ai_analyzer import analyze_syllabi_with_ai
from app.services.syllabus_comparator import compare_normalized_syllabi


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

        if schema_name == "syllabus_extraction":
            return {
                "metadata": {
                    "course_code": "2207",
                    "course_name": "TERMODINAMICA",
                    "nrc": "7542",
                    "semester": "202610",
                    "academic_period": "202610",
                    "source_file": "202610-ING-2207-NRC-7542-TERMODINAMICA.pdf",
                },
                "sections": {
                    "evaluaciones_y_ponderaciones": {
                        "found": True,
                        "page_numbers": [6],
                        "raw_evidence": "Pruebas 30, Examen 70",
                        "structured_data": {
                            "evaluations": [
                                {
                                    "type": "Pruebas",
                                    "quantity": 3,
                                    "weight_total": 30,
                                    "weight_each": 10,
                                    "description": "3 pruebas",
                                }
                            ]
                        },
                    },
                    "requisitos_aprobacion": {
                        "found": True,
                        "page_numbers": [8],
                        "raw_evidence": "Nota mínima de aprobación 4.0",
                        "structured_data": {
                            "minimum_final_grade": 4.0,
                            "minimum_exam_grade": 3.0,
                            "automatic_failure_rules": [],
                            "grade_cap_rules": [],
                            "attendance_rules": [],
                        },
                    },
                    "criterios_eximicion": {
                        "found": True,
                        "page_numbers": [8],
                        "raw_evidence": "Promedio igual o superior a 5,5",
                        "structured_data": {
                            "is_available": True,
                            "threshold": 5.5,
                            "conditions": ["Promedio igual o superior a 5,5"],
                        },
                    },
                    "nota_final": {
                        "found": True,
                        "page_numbers": [9],
                        "raw_evidence": "NF = 0.7 NP + 0.3 EX",
                        "structured_data": {
                            "presentation_grade_formula": "NP = ...",
                            "final_grade_formula": "NF = 0.7 NP + 0.3 EX",
                            "presentation_weight": 70,
                            "exam_weight": 30,
                        },
                    },
                },
                "warnings": [],
            }

        return {
            "course": {
                "course_code": "2207",
                "course_name": "TERMODINAMICA",
                "nrcs_compared": ["7542", "7543"],
            },
            "summary": {
                "total_syllabus_compared": 2,
                "total_inconsistencies": 1,
                "most_deviating_nrc": "7543",
                "severity_counts": {"critica": 1, "moderada": 0, "menor": 0},
                "possible_outlier": {"nrc": "7543", "alerts": 1, "reason": "Mayor diferencia"},
                "analysis_mode": "group_pattern",
            },
            "inconsistencies": [
                {
                    "section": "criterios_eximicion",
                    "variable": "threshold",
                    "severity": "critica",
                    "description": "Un NRC exige 5.8 y otro 5.5.",
                    "values_by_nrc": {"7542": 5.5, "7543": 5.8},
                    "majority_value": 5.5,
                    "outlier_nrcs": ["7543"],
                    "evidence": [
                        {"nrc": "7542", "page": 8, "text": "Promedio igual o superior a 5,5"},
                        {"nrc": "7543", "page": 8, "text": "Promedio igual o superior a 5,8"},
                    ],
                    "suggested_action": "Revisar el umbral de eximición del NRC 7543.",
                }
            ],
            "warnings": [],
        }


def test_ai_analyzer_uses_one_extraction_per_syllabus_and_one_global_comparison(monkeypatch):
    class FakeSettings:
        ai_max_pdf_text_chars = 5000
        local_model = "qwen2.5:14b"

    monkeypatch.setattr("app.services.ai_analyzer.get_settings", lambda: FakeSettings())

    client = FakeAIClient()
    syllabi = [
        FakeSyllabus(
            "7542",
            """
--- Página 1 ---
Información de la Asignatura
Carrera: ING
--- Página 6 ---
Evaluaciones y Ponderaciones
Pruebas 30
--- Página 8 ---
Requisitos de Aprobación
Nota mínima 4.0
Criterios de Eximición
Promedio igual o superior a 5,5
--- Página 9 ---
Nota Final de la Asignatura
NF = 0.7 NP + 0.3 EX
""".strip(),
        ),
        FakeSyllabus(
            "7543",
            """
--- Página 1 ---
Información de la Asignatura
Carrera: ING
--- Página 6 ---
Evaluaciones y Ponderaciones
Pruebas 30
--- Página 8 ---
Requisitos de Aprobación
Nota mínima 4.0
Criterios de Eximición
Promedio igual o superior a 5,8
--- Página 9 ---
Nota Final de la Asignatura
NF = 0.7 NP + 0.3 EX
""".strip(),
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

    extraction_calls = [call for call in client.calls if call["schema_name"] == "syllabus_extraction"]
    comparison_calls = [call for call in client.calls if call["schema_name"] == "syllabus_comparison"]

    assert len(extraction_calls) == 2
    assert len(comparison_calls) == 1
    assert result["summary"]["course"]["course_code"] == "2207"
    assert result["summary"]["severity_counts"]["Crítica"] == 1
    assert result["summary"]["possible_outlier"]["nrc"] == "7543"
    assert result["inconsistencies"][0]["severity"] == "critica"


def test_compare_normalized_syllabi_fills_missing_summary_fields():
    class MinimalClient:
        def complete_json(self, *, system_prompt, user_prompt, schema_name, schema):
            return {
                "course": {
                    "course_code": "2207",
                    "course_name": "TERMODINAMICA",
                    "nrcs_compared": ["7542", "7543"],
                },
                "summary": {
                    "total_syllabus_compared": 2,
                    "total_inconsistencies": 1,
                    "most_deviating_nrc": None,
                    "severity_counts": {"critica": 0, "moderada": 0, "menor": 0},
                    "possible_outlier": None,
                    "analysis_mode": "group_pattern",
                },
                "inconsistencies": [
                    {
                        "section": "requisitos_aprobacion",
                        "variable": "minimum_exam_grade",
                        "severity": "Critica",
                        "description": "Un NRC exige 3.5 y otro 3.0.",
                        "values_by_nrc": {"7542": 3.0, "7543": 3.5},
                        "majority_value": None,
                        "outlier_nrcs": [],
                        "evidence": [],
                        "suggested_action": "Revisar la regla de examen.",
                    }
                ],
                "warnings": [],
            }

    result = compare_normalized_syllabi(
        course_metadata={"course_code": "2207", "course_name": "TERMODINAMICA"},
        normalized_syllabi_by_nrc={
            "7542": {"metadata": {}, "sections": {}, "warnings": []},
            "7543": {"metadata": {}, "sections": {}, "warnings": []},
        },
        ai_client=MinimalClient(),
    )

    assert result["summary"]["most_deviating_nrc"] == "7543"
    assert result["summary"]["possible_outlier"]["nrc"] == "7543"
    assert result["inconsistencies"][0]["majority_value"] == 3.0
    assert result["inconsistencies"][0]["severity"] == "critica"


def test_compare_normalized_syllabi_discards_equivalent_rules_and_values():
    class EquivalentClient:
        def complete_json(self, *, system_prompt, user_prompt, schema_name, schema):
            return {
                "course": {
                    "course_code": "2207",
                    "course_name": "TERMODINAMICA",
                    "nrcs_compared": ["7587", "7588"],
                },
                "summary": {
                    "total_syllabus_compared": 2,
                    "total_inconsistencies": 1,
                    "most_deviating_nrc": "7588",
                    "severity_counts": {"critica": 1, "moderada": 0, "menor": 0},
                    "possible_outlier": {"nrc": "7588", "alerts": 1, "reason": "Mayor diferencia"},
                    "analysis_mode": "group_pattern",
                },
                "inconsistencies": [
                    {
                        "section": "requisitos_aprobacion",
                        "variable": "minimum_final_grade",
                        "severity": "critica",
                        "description": "Different minimum final grade requirements: NRC 7587: 4.0, NRC 7588: 4.0",
                        "values_by_nrc": {"7587": 4.0, "7588": 4.0},
                        "majority_value": 4.0,
                        "outlier_nrcs": ["7588"],
                        "evidence": [
                            {"nrc": "7587", "page": 8, "text": "Minimum final grade 4.0"},
                            {"nrc": "7588", "page": 8, "text": "Minimum final grade 4.0"},
                        ],
                        "suggested_action": "Review the minimum final grade policy.",
                    },
                    {
                        "section": "requisitos_aprobacion",
                        "variable": "automatic_failure_rules",
                        "severity": "critica",
                        "description": "Different automatic failure rules",
                        "values_by_nrc": {
                            "7587": "If the final grade is less than 3.0, the course is failed.",
                            "7588": "If final grade is less than 3.0, the course is failed.",
                        },
                        "majority_value": "If the final grade is less than 3.0, the course is failed.",
                        "outlier_nrcs": ["7588"],
                        "evidence": [],
                        "suggested_action": "Review the automatic failure rules.",
                    },
                ],
                "warnings": [],
            }

    result = compare_normalized_syllabi(
        course_metadata={"course_code": "2207", "course_name": "TERMODINAMICA"},
        normalized_syllabi_by_nrc={
            "7587": {"metadata": {}, "sections": {}, "warnings": []},
            "7588": {"metadata": {}, "sections": {}, "warnings": []},
        },
        ai_client=EquivalentClient(),
    )

    assert result["inconsistencies"] == []
    assert result["summary"]["total_inconsistencies"] == 0
    assert result["summary"]["severity_counts"] == {"Crítica": 0, "Moderada": 0, "Menor": 0}