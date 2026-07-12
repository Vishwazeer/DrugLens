import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.analyzer import analyze_medications, get_demo_cases, CONDITION_OPTIONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DrugLens API", description="API for Geriatric Polypharmacy Risk Analyzer")

# Configure CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
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
        return result
    except Exception as e:
        logger.error(f"Error during analysis: {e}")
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
