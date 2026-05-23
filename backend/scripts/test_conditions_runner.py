from pathlib import Path
import json

from app.services.conditions_formula_extractor import enrich_syllabi_with_conditions_export

class FakeClient:
    def __init__(self, response_rows):
        self.response = {"rows": response_rows}

    def complete_json(self, *, system_prompt, user_prompt, schema_name, schema):
        # ignore prompts, return predefined structure
        return self.response


def load_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        return path.read_bytes().decode('utf-8', errors='replace')


def main():
    base = Path(__file__).resolve().parents[1].parent / 'storage'
    files = [base / 'syllabus.md', base / 'syllabus2.md']

    normalized = {}
    for i, f in enumerate(files, start=1):
        text = load_text_file(f)
        nrc = f.stem + f'-{i}'
        normalized[nrc] = {
            "evaluaciones": [],
            "requisitos_aprobacion": "",
            "criterios_eximicion": "",
            "nota_final": text,
        }

    # Case A: AI returns empty fields -> should use our split logic (no long paragraph in nota_final)
    rows_a = [{"nrc": n, "requisitos_aprobacion": "", "requisitos_exencion": "", "nota_final": "", "nota_final_reprobados": "", "otros_criterios": ""} for n in normalized.keys()]
    client_a = FakeClient(rows_a)
    result_a = enrich_syllabi_with_conditions_export(normalized.copy(), client_a)

    # Case B: AI returns full paragraph mistakenly in nota_final -> before fix would appear in NOTA FINAL
    rows_b = [{"nrc": n, "requisitos_aprobacion": "", "requisitos_exencion": "", "nota_final": normalized[n]["nota_final"], "nota_final_reprobados": "", "otros_criterios": ""} for n in normalized.keys()]
    client_b = FakeClient(rows_b)
    result_b = enrich_syllabi_with_conditions_export(normalized.copy(), client_b)

    print("--- RESULT A (AI returned empty fields) ---")
    print(json.dumps({k: v.get('conditions_export') for k, v in result_a.items()}, ensure_ascii=False, indent=2) )
    print()
    print("--- RESULT B (AI returned full paragraph as nota_final) ---")
    print(json.dumps({k: v.get('conditions_export') for k, v in result_b.items()}, ensure_ascii=False, indent=2) )


if __name__ == '__main__':
    main()
