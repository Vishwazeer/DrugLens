"""DrugLens main analysis orchestrator.

Ties together parsing, interaction checking, prediction, and reporting.
Each pipeline step is wrapped in try/except so partial results are always returned.
"""

from src.drug_interactions import (
    check_interactions, check_beers_criteria, check_stopp_start, normalize_drug_name
)
from src.med_parser import parse_medications, extract_patient_info
from src.ddi_predictor import predict_unknown_interactions
from src.report_generator import generate_risk_report, generate_patient_summary
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def analyze_medications(
    medication_text: str,
    patient_age: int = 75,
    patient_conditions: list[str] = None,
    patient_egfr: Optional[float] = None,
    use_llm_parser: bool = True,
    use_txgemma: bool = True,
    use_gemma4: bool = True,
) -> dict:
    """Full analysis pipeline with graceful fallback at every step.

    Returns a dict with keys: medications, patient_info, interactions,
    beers_criteria, stopp_start, predicted_interactions, risk_report,
    patient_summary, errors, risk_level.
    """
    patient_conditions = patient_conditions or []
    errors: list[str] = []

    result = {
        "parsed_medications": [],
        "patient_info": {
            "age": patient_age,
            "conditions": patient_conditions,
            "egfr": patient_egfr,
        },
        "interactions": [],
        "beers_alerts": [],
        "stopp_start": {"stopp": [], "start": []},
        "predicted_interactions": [],
        "risk_report": {},
        "patient_summary": "",
        "errors": errors,
        "risk_level": "unknown",
        "risk_score": 0,
    }

    # --- Step 1: Parse medications ---
    try:
        medications = parse_medications(medication_text, use_llm=use_llm_parser)
        result["parsed_medications"] = medications
        logger.info("Parsed %d medications", len(medications))
    except Exception as e:
        errors.append(f"Medication parsing failed: {e}")
        logger.warning("Medication parsing failed: %s", e)
        # Build a minimal fallback: split on commas/newlines, wrap as dicts
        raw_items = [
            s.strip()
            for s in medication_text.replace("\n", ",").split(",")
            if s.strip()
        ]
        medications = [{"name": normalize_drug_name(item), "raw": item} for item in raw_items]
        result["parsed_medications"] = medications

    # --- Step 1b: Extract patient info from text if present ---
    try:
        extracted = extract_patient_info(medication_text)
        if extracted:
            # Merge extracted info but don't overwrite explicit args
            if not patient_conditions and extracted.get("conditions"):
                result["patient_info"]["conditions"] = extracted["conditions"]
            if patient_egfr is None and extracted.get("egfr") is not None:
                result["patient_info"]["egfr"] = extracted["egfr"]
    except Exception as e:
        errors.append(f"Patient info extraction failed: {e}")
        logger.warning("Patient info extraction failed: %s", e)

    drug_names = [
        m.get("name") or m.get("drug_name") or m.get("raw", "")
        for m in medications
    ]

    # --- Step 2: Check drug-drug interactions (local DB) ---
    try:
        interactions = check_interactions(drug_names)
        result["interactions"] = interactions
        logger.info("Found %d interactions", len(interactions))
    except Exception as e:
        errors.append(f"Interaction check failed: {e}")
        logger.warning("Interaction check failed: %s", e)

    # --- Step 3: Beers Criteria ---
    try:
        beers = check_beers_criteria(
            drug_names,
            patient_age=patient_age,
            conditions=patient_conditions,
        )
        result["beers_alerts"] = beers
        logger.info("Found %d Beers criteria flags", len(beers))
    except Exception as e:
        errors.append(f"Beers criteria check failed: {e}")
        logger.warning("Beers criteria check failed: %s", e)

    # --- Step 4: STOPP/START ---
    try:
        stopp = check_stopp_start(
            drug_names,
            patient_age=patient_age,
            conditions=patient_conditions,
        )
        result["stopp_start"] = stopp
        n_stopp = len(stopp.get("stopp", [])) + len(stopp.get("start", []))
        logger.info("Found %d STOPP/START flags", n_stopp)
    except Exception as e:
        errors.append(f"STOPP/START check failed: {e}")
        logger.warning("STOPP/START check failed: %s", e)

    # --- Step 5: Predict unknown DDIs via TxGemma ---
    if use_txgemma:
        try:
            predicted = predict_unknown_interactions(drug_names)
            result["predicted_interactions"] = predicted
            logger.info("TxGemma predicted %d interactions", len(predicted))
        except Exception as e:
            errors.append(f"TxGemma prediction failed: {e}")
            logger.warning("TxGemma prediction failed: %s", e)

    # --- Step 6: Generate risk report via Gemma 4 ---
    if use_gemma4:
        try:
            report = generate_risk_report(
                medications=result["parsed_medications"],
                interactions=result["interactions"],
                beers_alerts=result["beers_alerts"],
                stopp_start=result["stopp_start"],
                predicted_ddis=result["predicted_interactions"],
                patient_info=result["patient_info"],
            )
            result["risk_report"] = report
        except Exception as e:
            errors.append(f"Risk report generation failed: {e}")
            logger.warning("Risk report generation failed: %s", e)

    # --- Step 7: Generate patient summary ---
    try:
        summary = generate_patient_summary(
            risk_report=result["risk_report"] if isinstance(result["risk_report"], dict) else {},
            medications=result["parsed_medications"],
        )
        result["patient_summary"] = summary
    except Exception as e:
        errors.append(f"Patient summary generation failed: {e}")
        logger.warning("Patient summary generation failed: %s", e)

    # --- Compute overall risk level ---
    result["risk_level"] = _compute_risk_level(result)

    return result


def _compute_risk_level(result: dict) -> str:
    """Derive an overall risk level from all findings.

    Scoring:
      - Each interaction adds points by severity (high=3, moderate=2, low=1)
      - Each Beers flag adds 2
      - Each STOPP flag adds 2
      - Each predicted interaction adds 1
    Thresholds: >=8 HIGH, >=4 MODERATE, else LOW
    """
    score = 0

    for ix in result.get("interactions", []):
        sev = (ix.get("severity") or "").lower()
        if sev == "high" or sev == "major":
            score += 3
        elif sev == "moderate":
            score += 2
        else:
            score += 1

    score += len(result.get("beers_alerts", [])) * 2
    stopp_data = result.get("stopp_start", {})
    if isinstance(stopp_data, dict):
        score += len(stopp_data.get("stopp", [])) * 2
    else:
        score += len(stopp_data) * 2
    score += len(result.get("predicted_interactions", []))

    result["risk_score"] = score

    if score >= 8:
        return "HIGH"
    elif score >= 4:
        return "MODERATE"
    elif score > 0:
        return "LOW"
    return "MINIMAL"


def get_demo_cases() -> list[dict]:
    """Three pre-built clinically realistic demo cases for judges."""
    return [
        {
            "name": "Case 1 — Mild (Hypertension + Diabetes)",
            "description": (
                "70-year-old with well-controlled hypertension and type 2 diabetes. "
                "Simple regimen, minimal interaction risk. Demonstrates that the "
                "system correctly identifies a LOW-risk patient."
            ),
            "medication_text": (
                "metformin 500mg twice daily\n"
                "lisinopril 10mg once daily\n"
                "amlodipine 5mg once daily"
            ),
            "patient_age": 70,
            "conditions": ["hypertension", "type 2 diabetes"],
            "expected_risk": "LOW",
        },
        {
            "name": "Case 2 — Moderate (Polypharmacy + GI/CV Risk)",
            "description": (
                "78-year-old with osteoarthritis, GERD, hypertension, and depression. "
                "Triggers NSAID + ACE-inhibitor interaction (renal risk), long-term PPI "
                "flagged by Beers Criteria, and the 'triple whammy' combination "
                "(NSAID + ACE-inhibitor + diuretic risk). Sertraline + ibuprofen raises "
                "GI bleeding risk."
            ),
            "medication_text": (
                "omeprazole 20mg once daily\n"
                "ibuprofen 400mg three times daily\n"
                "lisinopril 20mg once daily\n"
                "sertraline 50mg once daily\n"
                "acetaminophen 500mg as needed"
            ),
            "patient_age": 78,
            "conditions": ["osteoarthritis", "GERD", "hypertension", "depression"],
            "expected_risk": "MODERATE",
        },
        {
            "name": "Case 3 — Severe (High-Risk Polypharmacy)",
            "description": (
                "85-year-old with atrial fibrillation, anxiety, insomnia, chronic pain, "
                "and heart failure on 8 medications. Triggers: warfarin + amiodarone "
                "(major bleed risk, INR elevation), digoxin + amiodarone (digoxin "
                "toxicity), opioid + benzodiazepine (respiratory depression — FDA "
                "black box), multiple CNS depressants (oxycodone + lorazepam + "
                "diphenhydramine), high anticholinergic burden, and several Beers "
                "Criteria flags (benzodiazepine in elderly, first-generation "
                "antihistamine, digoxin >0.125mg in elderly). STOPP flags for "
                "benzodiazepine fall risk and long-acting opioid without laxative."
            ),
            "medication_text": (
                "warfarin 5mg once daily\n"
                "digoxin 0.25mg once daily\n"
                "amiodarone 200mg once daily\n"
                "lorazepam 1mg twice daily\n"
                "oxycodone 5mg every 6 hours\n"
                "diphenhydramine 25mg at bedtime\n"
                "furosemide 40mg once daily\n"
                "potassium chloride 20mEq once daily"
            ),
            "patient_age": 85,
            "conditions": [
                "atrial fibrillation",
                "anxiety",
                "insomnia",
                "chronic pain",
                "heart failure",
            ],
            "expected_risk": "HIGH",
        },
    ]
