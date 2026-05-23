from app.services.conditions_formula_extractor import enrich_syllabi_with_conditions_export


class FakeClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, *, system_prompt, user_prompt, schema_name, schema):
        self.calls.append({"schema_name": schema_name, "user_prompt": user_prompt})
        return {
            "nrc": "7579",
            "requisitos_aprobacion": "NF >= 4.0",
            "requisitos_eximicion": None,
            "formula_nota_final": "NF = 0.7 NP + 0.3 EX. Si EX < 3.0 reprueba.",
            "nota_final_reprobacion": "Si EX < 3.0 -> reprueba",
            "otros_criterios": None,
            "evidencia_textual": [
                {"campo": "formula_nota_final", "fragmento": "NF = 0.7 NP + 0.3 EX"}
            ],
            "confianza_extraccion": 0.9,
            "advertencias": [],
        }


def test_conditions_formula_extractor_preserves_decimal_formula(monkeypatch):
    monkeypatch.setattr(
        "app.services.conditions_formula_extractor.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "conditions_export_max_workers": 1,
                "conditions_export_batch_max_syllabi": 3,
                "conditions_export_batch_max_chars": 12000,
                "analysis_max_retries": 1,
                "analysis_retry_delay_seconds": 0,
            },
        )(),
    )

    result = enrich_syllabi_with_conditions_export(
        {
            "7579": {
                "evaluaciones": [],
                "requisitos_aprobacion": "",
                "criterios_eximicion": "",
                "nota_final": "NF = 0.7 NP + 0.3 EX",
            }
        },
        FakeClient(),
    )

    export = result["7579"]["conditions_export"]
    assert export["formula_nota_final"] == "NF = 0.7 NP + 0.3 EX"
    assert export["nota_final"] == "NF = 0.7 NP + 0.3 EX"
    assert export["formula_nota_final"] != "NF = 0"


class FakeBatchClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, *, system_prompt, user_prompt, schema_name, schema):
        self.calls.append({"schema_name": schema_name, "user_prompt": user_prompt})
        return {
            "rows": [
                {
                    "nrc": "7579",
                    "requisitos_aprobacion": "NF >= 4.0",
                    "requisitos_eximicion": None,
                    "formula_nota_final": "NF = 0.7 NP + 0.3 EX",
                    "nota_final_reprobacion": None,
                    "otros_criterios": None,
                    "evidencia_textual": [
                        {"campo": "formula_nota_final", "fragmento": "NF = 0.7 NP + 0.3 EX"}
                    ],
                    "confianza_extraccion": 0.9,
                    "advertencias": [],
                },
                {
                    "nrc": "7580",
                    "requisitos_aprobacion": "NF >= 4.0",
                    "requisitos_eximicion": "NP >= 5.5",
                    "formula_nota_final": "NF = 0.6 NP + 0.4 EX",
                    "nota_final_reprobacion": "Si EX < 3.0 -> NF = 3.9",
                    "otros_criterios": None,
                    "evidencia_textual": [
                        {"campo": "formula_nota_final", "fragmento": "NF = 0.6 NP + 0.4 EX"}
                    ],
                    "confianza_extraccion": 0.9,
                    "advertencias": [],
                },
            ]
        }


def test_conditions_formula_extractor_uses_batch_for_small_payloads(monkeypatch):
    monkeypatch.setattr(
        "app.services.conditions_formula_extractor.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "conditions_export_max_workers": 4,
                "conditions_export_batch_max_syllabi": 3,
                "conditions_export_batch_max_chars": 12000,
                "analysis_max_retries": 1,
                "analysis_retry_delay_seconds": 0,
            },
        )(),
    )

    client = FakeBatchClient()
    result = enrich_syllabi_with_conditions_export(
        {
            "7579": {
                "evaluaciones": [],
                "requisitos_aprobacion": "",
                "criterios_eximicion": "",
                "nota_final": "NF = 0.7 NP + 0.3 EX",
            },
            "7580": {
                "evaluaciones": [],
                "requisitos_aprobacion": "",
                "criterios_eximicion": "",
                "nota_final": "NF = 0.6 NP + 0.4 EX",
            },
        },
        client,
    )

    assert [call["schema_name"] for call in client.calls] == ["conditions_export_batch"]
    assert result["7579"]["conditions_export"]["formula_nota_final"] == "NF = 0.7 NP + 0.3 EX"
    assert result["7580"]["conditions_export"]["formula_nota_final"] == "NF = 0.6 NP + 0.4 EX"
