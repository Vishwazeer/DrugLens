import json
import logging
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src import config
from src.analyzer import CONDITION_OPTIONS, analyze_medications, get_demo_cases
from src.ddi_predictor import predict_unknown_interactions_cloud
from src.drug_interactions import _load_json, load_interaction_db
from src.router import (
    ROUTE_CLOUD,
    decide_route,
    generate_alternatives,
    stream_clinical_narrative,
)

# Friendly short name of the configured cloud model, e.g. "deepseek-v4-pro"
_CLOUD_MODEL_LABEL = config.REPORT_MODEL.split("/")[-1]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DrugLens API", description="API for Geriatric Polypharmacy Risk Analyzer")

# Configure CORS for React frontend — must be added BEFORE any routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # must be False when allow_origins=["*"]
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)

@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str, request: Request) -> Response:
    """Catch-all OPTIONS handler for CORS preflight requests."""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )

class AnalyzeRequest(BaseModel):
    medication_text: str
    patient_age: int = 75
    patient_conditions: list[str] | None = None
    patient_egfr: float | None = None
    # Default the local-vLLM toggles from the deployment's feature flags so the
    # API is CPU-safe out of the box (no MedGemma/TxGemma connection attempts
    # unless a GPU pod sets USE_LLM_PARSER / USE_TXGEMMA). The frontend still
    # overrides use_gemma4 from its toggle.
    use_llm_parser: bool = config.USE_LLM_PARSER
    use_txgemma: bool = config.USE_TXGEMMA
    use_gemma4: bool = config.USE_GEMMA4

@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest):
    try:
        result = analyze_medications(
            medication_text=request.medication_text,
            patient_age=request.patient_age,
            patient_conditions=request.patient_conditions or [],
            patient_egfr=request.patient_egfr,
            use_llm_parser=request.use_llm_parser,
            use_txgemma=request.use_txgemma,
            use_gemma4=request.use_gemma4,
        )
        # Attach routing metadata so the frontend can show the hardware indicator
        route = decide_route(result.get("risk_level", "MINIMAL"))
        result["routing"] = {
            "route": route,
            # Report only what we can actually demonstrate: that the answer came
            # from the cloud model on Fireworks, or from the offline engine.
            # (We do not claim specific silicon we cannot verify from here.)
            "engine": "Cloud LLM via Fireworks AI" if route == ROUTE_CLOUD else "Edge Engine (Offline)",
            "model": _CLOUD_MODEL_LABEL if route == ROUTE_CLOUD else None,
        }
        return result
    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/analyze/stream-narrative")
async def stream_narrative(request: AnalyzeRequest):
    """SSE endpoint that streams a Fireworks AI clinical narrative token-by-token.

    Only called for MODERATE/HIGH risk cases (token-efficient routing).
    Returns text/event-stream.
    """
    try:
        # Run full analysis first
        result = analyze_medications(
            medication_text=request.medication_text,
            patient_age=request.patient_age,
            patient_conditions=request.patient_conditions or [],
            patient_egfr=request.patient_egfr,
            use_llm_parser=request.use_llm_parser,
            use_txgemma=request.use_txgemma,
            use_gemma4=False,  # Skip the non-streaming Gemma4 call; we'll stream instead
        )

        async def event_generator():
            # First send routing metadata as a special event
            route = decide_route(result.get("risk_level", "MINIMAL"))
            meta = {
                "type": "meta",
                "risk_level": result.get("risk_level"),
                "risk_score": result.get("risk_score"),
                "route": route,
            }
            yield f"data: {json.dumps(meta)}\n\n"

            # Stream clinical narrative only for HIGH/MODERATE
            if route == ROUTE_CLOUD:
                async for chunk in stream_clinical_narrative(result):
                    payload = {"type": "chunk", "text": chunk}
                    yield f"data: {json.dumps(payload)}\n\n"
            else:
                # Edge-only: emit a short deterministic summary
                yield f"data: {json.dumps({'type': 'chunk', 'text': 'Low-risk profile confirmed by offline deterministic engine. No LLM inference required.'})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Access-Control-Allow-Origin": "*",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        logger.error(f"Error during streaming: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/analyze/alternatives")
async def get_alternatives(request: AnalyzeRequest):
    """Generate structured JSON prescribing alternatives via Fireworks AI.

    Uses the Fireworks cloud model to produce safer alternatives for each flagged medication,
    demonstrating structured JSON extraction from open-weights LLMs.
    """
    try:
        result = analyze_medications(
            medication_text=request.medication_text,
            patient_age=request.patient_age,
            patient_conditions=request.patient_conditions or [],
            patient_egfr=request.patient_egfr,
            use_llm_parser=request.use_llm_parser,
            use_txgemma=request.use_txgemma,
            use_gemma4=False,
        )
        alternatives = generate_alternatives(result)
        return {"alternatives": alternatives, "risk_level": result.get("risk_level")}
    except Exception as e:
        logger.error(f"Error generating alternatives: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/demo-cases")
async def demo_cases():
    return get_demo_cases()

@app.get("/api/conditions")
async def conditions():
    return CONDITION_OPTIONS

@app.post("/api/analyze/predict-novel")
async def predict_novel(request: AnalyzeRequest):
    """Predict interactions for drug pairs that are NOT in the curated database.

    This is the "novel drug blindspot" that lookup-table checkers miss: they can
    only flag pairs someone already indexed. Every unindexed pair here is
    evaluated by the cloud model, grounded in PubChem molecular structures.

    Kept as its own endpoint so /api/analyze stays fast (~1s).
    """
    try:
        result = analyze_medications(
            medication_text=request.medication_text,
            patient_age=request.patient_age,
            patient_conditions=request.patient_conditions or [],
            patient_egfr=request.patient_egfr,
            use_llm_parser=request.use_llm_parser,
            use_txgemma=False,
            use_gemma4=False,
        )
        drug_names = [
            m.get("name") or m.get("raw", "") for m in result.get("parsed_medications", [])
        ]
        known = result.get("interactions", [])
        predictions = predict_unknown_interactions_cloud(drug_names, known)

        total_pairs = len(drug_names) * (len(drug_names) - 1) // 2
        return {
            "predictions": predictions,
            "pairs_in_database": len(known),
            "pairs_evaluated": max(total_pairs - len(known), 0),
            "model": _CLOUD_MODEL_LABEL,
        }
    except Exception as e:
        logger.error(f"Error predicting novel interactions: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/engine-stats")
async def engine_stats():
    """Real, live counts read from the loaded rulesets — never hardcoded.

    The UI renders these, so the numbers it shows can always be checked
    against data/*.json. Latency is genuinely measured here, not asserted.
    """
    beers = _load_json("beers_criteria.json", [])
    ss = _load_json("stopp_start.json", {"stopp": [], "start": []})
    ddi = load_interaction_db()

    # Measure the deterministic engine on a representative regimen.
    sample = "warfarin 5mg daily\namiodarone 200mg daily\nlorazepam 1mg bid\noxycodone 5mg q6h"
    timings: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        analyze_medications(
            medication_text=sample,
            patient_age=85,
            patient_conditions=["Atrial Fibrillation"],
            use_llm_parser=False,
            use_txgemma=False,
            use_gemma4=False,
        )
        timings.append((time.perf_counter() - t0) * 1000)
    timings.sort()

    return {
        "ddi_pairs": len(ddi),
        "beers_rules": len(beers),
        "stopp_rules": len(ss.get("stopp", [])),
        "start_rules": len(ss.get("start", [])),
        "stopp_start_total": len(ss.get("stopp", [])) + len(ss.get("start", [])),
        "conditions": len(CONDITION_OPTIONS),
        "median_engine_latency_ms": round(timings[len(timings) // 2], 1),
    }


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


# Serve the built React app (frontend/dist) from the same origin when it exists,
# so a single container can serve both the API and the UI. Mounted last so the
# /api/* routes above always take precedence. In dev the Vite server handles the
# UI instead and this mount is simply absent.
_DIST = Path(__file__).parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
