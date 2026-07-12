import json
import logging
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
            "engine": "AMD Instinct™ MI300X via Fireworks AI" if route == ROUTE_CLOUD else "Edge Engine (Offline)",
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
