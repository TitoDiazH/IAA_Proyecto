from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json

app = FastAPI()


@app.get("/api/models")
async def models():
    return JSONResponse([{"name": "qwen2.5:14b"}])


@app.post("/api/chat")
async def chat(req: Request):
    payload = await req.json()
    # Look into messages for user text
    messages = payload.get("messages") or []
    user_text = " ".join(m.get("content", "") for m in messages)

    # Simple heuristics: detect comparison prompt vs extraction
    if "Recortes relevantes" in user_text or "Recortes" in user_text or "Comparación" in user_text:
        comparison = {
            "analysis_mode": "pairwise",
            "compared_nrcs": ["0001", "0002"],
            "overall_summary": "Mock: diferencias detectadas en criterios.",
            "severity_counts": {"Crítica": 1},
            "possible_outlier": {"nrc": "0002", "alert_count": 1, "reason": "Formato distinto"},
            "inconsistencies": [
                {
                    "section": "Criterios de Eximición",
                    "variable": "Umbral de eximición",
                    "difference": "0001 exige 5.5, 0002 exige 5.8",
                    "involved_nrcs": ["0001", "0002"],
                    "severity": "Crítica",
                    "priority_rationale": "Impacta eximición",
                    "suggestion": "Revisar y unificar",
                    "evidence": "Extracción mock",
                    "is_main_alert": True,
                }
            ],
        }
        return JSONResponse({"message": {"content": json.dumps(comparison)}})

    # Section extraction heuristic
    # Return a plausible extraction JSON string
    extraction = {
        "section_name": "Criterios de Eximición",
        "section_found": True,
        "confidence": 0.95,
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
        "academic_interpretation": "Regla explicita de eximición.",
    }

    return JSONResponse({"message": {"content": json.dumps(extraction)}})
