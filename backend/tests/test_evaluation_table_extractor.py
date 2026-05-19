from decimal import Decimal

from app.services.ai_analyzer import _build_evaluation_table_comparison
from app.services.evaluation_table_extractor import (
    VisualRow,
    format_weight_map,
    parse_evaluation_items_from_rows,
    weight_map_from_items,
)


def row(text, page=1, y0=100):
    return VisualRow(page=page, y0=y0, text=text, words=())


def test_parse_evaluation_rows_ignores_order_and_sums_repeated_tests():
    items = parse_evaluation_items_from_rows(
        [
            row("Evaluaciones y Ponderaciones"),
            row("Tipo Cantidad Ponderación"),
            row("Prueba 1 17.5%"),
            row("Prueba 2 17,5%"),
            row("Prueba 3 17.5%"),
            row("Examen Final 30%"),
        ]
    )

    weights = weight_map_from_items(items)

    assert weights["pruebas"] == Decimal("52.5")
    assert weights["examen final"] == Decimal("30")
    assert format_weight_map(weights) == "Examen Final: 30%, Pruebas: 52.5%"


def test_structured_evaluation_comparison_does_not_report_reordered_weights():
    extracted_by_nrc = {
        "7587": {
            "sections": {
                "evaluations": {
                    "structured_data": {
                        "weight_map": {"examen final": "30", "pruebas": "52.5"}
                    }
                }
            }
        },
        "7588": {
            "sections": {
                "evaluations": {
                    "structured_data": {
                        "weight_map": {"pruebas": "52.5", "examen final": "30"}
                    }
                }
            }
        },
    }

    result = _build_evaluation_table_comparison(extracted_by_nrc, ["7587", "7588"])

    assert result is not None
    assert result["inconsistencies"] == []
    assert result["severity_counts"] == {"critica": 0, "moderada": 0, "menor": 0}


def test_structured_evaluation_comparison_reports_real_weight_difference():
    extracted_by_nrc = {
        "7587": {
            "sections": {
                "evaluations": {
                    "structured_data": {
                        "weight_map": {"examen final": "30", "pruebas": "52.5"}
                    }
                }
            }
        },
        "7588": {
            "sections": {
                "evaluations": {
                    "structured_data": {
                        "weight_map": {"examen final": "40", "pruebas": "42.5"}
                    }
                }
            }
        },
    }

    result = _build_evaluation_table_comparison(extracted_by_nrc, ["7587", "7588"])

    assert result is not None
    assert result["severity_counts"]["critica"] == 2
    assert {item["variable"] for item in result["inconsistencies"]} == {
        "Ponderación de Examen Final",
        "Ponderación de Pruebas",
    }
