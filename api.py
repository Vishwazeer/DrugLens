import json
import logging
from typing import List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from src.analyzer import analyze_medications, get_demo_cases, CONDITION_OPTIONS
from src.router import decide_route, stream_clinical_narrative, generate_alternatives, ROUTE_EDGE, ROUTE_CLOUD

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
    patient_conditions: Optional[List[str]] = None
    patient_egfr: Optional[float] = None
    use_llm_parser: bool = True
    use_txgemma: bool = True
    use_gemma4: bool = True

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
            "model": "Gemma 4 31B" if route == ROUTE_CLOUD else None,
        }
        return result
    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze/alternatives")
async def get_alternatives(request: AnalyzeRequest):
    """Generate structured JSON prescribing alternatives via Fireworks AI.

    Uses Gemma 4 to produce safer alternatives for each flagged medication,
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/demo-cases")
async def demo_cases():
    return get_demo_cases()

@app.get("/api/conditions")
async def conditions():
    return CONDITION_OPTIONS

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
