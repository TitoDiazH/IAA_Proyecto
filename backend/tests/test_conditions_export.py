from zipfile import ZipFile
from io import BytesIO

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AnalysisReport, CourseGroup, Syllabus
from app.services.conditions_export import (
    build_conditions_export_table,
    conditions_table_to_xlsx,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_build_conditions_export_table_uses_completed_report_normalized_data():
    db = make_session()
    course = CourseGroup(
        academic_period="202610",
        year=2026,
        term="10",
        course_code="ING1108",
        career="ING",
        course_name="Introduccion al Calculo",
    )
    db.add(course)
    db.flush()
    db.add(
        Syllabus(
            course_group_id=course.id,
            original_filename="202610-ING-ING1108-NRC-7579-INTRODUCCION-AL-CALCULO.pdf",
            stored_path="/tmp/syllabus.pdf",
            file_size=100,
            academic_period="202610",
            year=2026,
            term="10",
            career="ING",
            course_code="ING1108",
            nrc="7579",
            course_name="Introduccion al Calculo",
            text_content="",
            extraction_status="ok",
        )
    )
    db.add(
        AnalysisReport(
            course_group_id=course.id,
            status="completed",
            compared_nrcs=["7579"],
            summary={
                "normalized_syllabi_by_nrc": {
                    "7579": {
                        "evaluaciones": [
                            {"tipo": "Controles", "ponderacion": 10.5, "descripcion": "3 controles"},
                            {"tipo": "Pruebas", "ponderacion": 59.5, "descripcion": "3 pruebas"},
                            {"tipo": "Examen", "ponderacion": 30, "descripcion": "1 examen"},
                        ],
                        "requisitos_aprobacion": "NP>=3; NE>=3; NF>=4",
                        "nota_final": "NF = 0.70 NP + 0.30 NE. Si NE<3, NF=min(3.9; NF).",
                        "conditions_export": {
                            "requisitos_aprobacion": "NP>=3; NE>=3; NF>=4",
                            "requisitos_exencion": "-",
                            "formula_nota_final": "NF=0.7NP+0.3NE",
                            "nota_final_reprobados": "Si NE<3 -> NF=min(3.9,NF)",
                            "otros_criterios": "",
                            "evidencia_textual": [
                                {"campo": "formula_nota_final", "fragmento": "NF = 0.70 NP + 0.30 NE"}
                            ],
                            "confianza_extraccion": 0.95,
                        },
                    }
                }
            },
            processing_time_seconds=1,
        )
    )
    db.commit()

    table = build_conditions_export_table(db)

    assert table["row_count"] == 1
    assert table["rows"][0][:7] == [
        "Introduccion al Calculo",
        "ING1108",
        "7579",
        "10.5%",
        "3",
        "59.5%",
        "3",
    ]
    assert table["rows"][0][12:15] == ["30%", "1", "NP>=3; NE>=3; NF>=4"]
    assert table["rows"][0][15:18] == [
        "-",
        "NF=0.7NP+0.3NE",
        "Si NE<3 -> NF=min(3.9,NF)",
    ]
    assert "Evidencia Textual" not in table["columns"]
    assert "Confianza Extracción" not in table["columns"]
    assert len(table["rows"][0]) == len(table["columns"]) == 19


def test_build_conditions_export_table_assigns_unknown_evaluation_to_other():
    db = make_session()
    course = CourseGroup(
        academic_period="202610",
        year=2026,
        term="10",
        course_code="ING1108",
        career="ING",
        course_name="Introduccion al Calculo",
    )
    db.add(course)
    db.flush()
    db.add(
        Syllabus(
            course_group_id=course.id,
            original_filename="202610-ING-ING1108-NRC-7579-INTRODUCCION-AL-CALCULO.pdf",
            stored_path="/tmp/syllabus.pdf",
            file_size=100,
            academic_period="202610",
            year=2026,
            term="10",
            career="ING",
            course_code="ING1108",
            nrc="7579",
            course_name="Introduccion al Calculo",
            text_content="",
            extraction_status="ok",
        )
    )
    db.add(
        AnalysisReport(
            course_group_id=course.id,
            status="completed",
            compared_nrcs=["7579"],
            summary={
                "normalized_syllabi_by_nrc": {
                    "7579": {
                        "evaluaciones": [
                            {"tipo": "Proyectos", "ponderacion": 80, "descripcion": "Impact Project"},
                            {"tipo": "Pruebas", "ponderacion": 20, "descripcion": "Examen"},
                            {"categoria": "Actividad especial", "ponderacion": 5},
                        ],
                        "requisitos_aprobacion": "",
                        "nota_final": "",
                    }
                }
            },
            processing_time_seconds=1,
        )
    )
    db.commit()

    table = build_conditions_export_table(db)

    assert table["rows"][0][5:7] == ["20%", "1"]
    assert table["rows"][0][10:12] == ["85%", "Impact Project; Actividad especial"]
    assert table["rows"][0][12:14] == ["", ""]


def test_conditions_table_to_xlsx_returns_openxml_zip():
    table = {
        "header_rows": [["Curso"], ["Codigo"], ["NRC"]],
        "columns": ["NRC"],
        "rows": [["7579"]],
    }

    payload = conditions_table_to_xlsx(table)

    with ZipFile(BytesIO(payload)) as archive:
        assert "xl/workbook.xml" in archive.namelist()
        assert "xl/worksheets/sheet1.xml" in archive.namelist()
        assert "xl/styles.xml" in archive.namelist()

        content_types = archive.read("[Content_Types].xml").decode()
        relationships = archive.read("xl/_rels/workbook.xml.rels").decode()
        styles = archive.read("xl/styles.xml").decode()
        worksheet = archive.read("xl/worksheets/sheet1.xml").decode()

        assert "/xl/styles.xml" in content_types
        assert "relationships/styles" in relationships
        assert "FF156082" in styles
        assert "FF0B3041" in styles
        assert 'state="frozen"' in worksheet


def test_conditions_table_to_xlsx_matches_reference_layout_groups():
    table = {
        "header_rows": [
            ["", "", "", "NOTA PRESENTACIÓN (NP)", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "", "", "Controles y/o Tareas", "", "Pruebas", "", "Laboratorio (NL)", "", "Taller HT", "Otro", "", "Examen (NE)", "", "", "", "", "", ""],
            [
                "Curso",
                "Codigo",
                "NRC",
                "Pond",
                "Cant",
                "Pond",
                "Cant",
                "Pond",
                "Cant",
                "Pond",
                "Pond",
                "Desc",
                "Pond",
                "Cant",
                "Requisitos Aprobación",
                "Requisitos Exención",
                "NOTA FINAL",
                "NOTA FINAL REPROBADOS",
                "Otros Criterios",
            ],
        ],
        "columns": ["NRC"],
        "rows": [["Curso", "ING1108", "7579", "10.5%", "3", "59.5%", "3", "", "", "", "", "", "30%", "1", "NF>=4", "NP>=5.5", "NF=0.7NP+0.3EX", "", ""]],
    }

    payload = conditions_table_to_xlsx(table)

    with ZipFile(BytesIO(payload)) as archive:
        worksheet = archive.read("xl/worksheets/sheet1.xml").decode()

        assert '<mergeCell ref="D1:L1"/>' in worksheet
        assert '<mergeCell ref="D2:E2"/>' in worksheet
        assert '<mergeCell ref="F2:G2"/>' in worksheet
        assert '<mergeCell ref="H2:I2"/>' in worksheet
        assert '<mergeCell ref="K2:L2"/>' in worksheet
        assert '<mergeCell ref="M2:N2"/>' in worksheet
        assert '<col min="16" max="16" width="67.9" customWidth="1"/>' in worksheet


def test_conditions_export_fallback_does_not_break_decimal_formula():
    db = make_session()
    course = CourseGroup(
        academic_period="202610",
        year=2026,
        term="10",
        course_code="ING1108",
        career="ING",
        course_name="Introduccion al Calculo",
    )
    db.add(course)
    db.flush()
    db.add(
        Syllabus(
            course_group_id=course.id,
            original_filename="202610-ING-ING1108-NRC-7579-INTRODUCCION-AL-CALCULO.pdf",
            stored_path="/tmp/syllabus.pdf",
            file_size=100,
            academic_period="202610",
            year=2026,
            term="10",
            career="ING",
            course_code="ING1108",
            nrc="7579",
            course_name="Introduccion al Calculo",
            text_content="",
            extraction_status="ok",
        )
    )
    db.add(
        AnalysisReport(
            course_group_id=course.id,
            status="completed",
            compared_nrcs=["7579"],
            summary={
                "normalized_syllabi_by_nrc": {
                    "7579": {
                        "evaluaciones": [],
                        "requisitos_aprobacion": "",
                        "nota_final": "NF = 0.7 NP + 0.3 EX. Si EX < 3.0 reprueba.",
                    }
                }
            },
            processing_time_seconds=1,
        )
    )
    db.commit()

    table = build_conditions_export_table(db)

    assert table["rows"][0][16] == "NF = 0.7 NP + 0.3 EX"
    assert table["rows"][0][16] != "NF = 0"
