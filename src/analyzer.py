"""DrugLens main analysis orchestrator.

Ties together parsing, interaction checking, prediction, and reporting.
Each pipeline step is wrapped in try/except so partial results are always
returned.
"""

import logging

from src.ddi_predictor import predict_unknown_interactions
from src.drug_interactions import (
    check_beers_criteria,
    check_interactions,
    check_stopp_start,
    normalize_drug_name,
)
from src.med_parser import extract_patient_info, parse_medications
from src.report_generator import generate_patient_summary, generate_risk_report

logger = logging.getLogger(__name__)

# Single source of truth for the patient-conditions vocabulary. The UI
# multiselect renders exactly these labels, and demo cases must use them.
CONDITION_OPTIONS: list[str] = [
    "Hypertension", "Diabetes Type 2", "Heart Failure", "Atrial Fibrillation",
    "COPD", "Osteoarthritis", "GERD", "Depression", "Anxiety", "Insomnia",
    "Chronic Kidney Disease", "Osteoporosis", "Dementia", "Parkinson's Disease",
    "Hypothyroidism", "Gout", "Epilepsy", "Asthma", "Coronary Artery Disease",
    "Peripheral Artery Disease", "DVT/PE", "Chronic Pain",
]

# Risk weights: interactions by DDI severity, criteria alerts by alert severity
_INTERACTION_WEIGHTS = {"major": 3, "high": 3, "moderate": 2}
_ALERT_WEIGHTS = {"high": 2}
_PREDICTED_WEIGHT = 1

# Score thresholds for the overall risk level
_HIGH_THRESHOLD = 12
_MODERATE_THRESHOLD = 5


def analyze_medications(
    medication_text: str,
    patient_age: int = 75,
    patient_conditions: list[str] | None = None,
    patient_egfr: float | None = None,
    use_llm_parser: bool = True,
    use_txgemma: bool = True,
    use_gemma4: bool = True,
) -> dict:
    """Full analysis pipeline with graceful fallback at every step.

    Returns a dict with keys: parsed_medications, patient_info {age,
    conditions, egfr}, interactions, beers_alerts, stopp_start {stopp,
    start}, predicted_interactions, risk_report, patient_summary, errors,
    risk_level (HIGH|MODERATE|LOW|MINIMAL), risk_score.
    """
    patient_conditions = patient_conditions or []
    errors: list[str] = []

    result: dict = {
        "parsed_medications": [],
        "patient_info": {
            "age": patient_age,
            "conditions": list(patient_conditions),
            "egfr": patient_egfr,
        },
        "interactions": [],
        "beers_alerts": [],
        "stopp_start": {"stopp": [], "start": []},
        "predicted_interactions": [],
        "risk_report": {},
        "patient_summary": "",
        "errors": errors,
        "risk_level": "UNKNOWN",
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

    # --- Step 1b: Merge patient info extracted from free text ---
    # Explicit arguments always win; extracted values fill the gaps, and
    # extracted conditions are unioned in so pasted clinical notes still
    # drive STOPP/START and Beers condition gates.
    try:
        extracted = extract_patient_info(medication_text)
        existing_lower = {c.lower() for c in result["patient_info"]["conditions"]}
        for cond in extracted.get("conditions", []):
            if cond.lower() not in existing_lower:
                result["patient_info"]["conditions"].append(cond)
                existing_lower.add(cond.lower())
        if patient_egfr is None and extracted.get("egfr") is not None:
            result["patient_info"]["egfr"] = extracted["egfr"]
    except Exception as e:
        errors.append(f"Patient info extraction failed: {e}")
        logger.warning("Patient info extraction failed: %s", e)

    effective_conditions: list[str] = result["patient_info"]["conditions"]
    effective_egfr: float | None = result["patient_info"]["egfr"]

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
            conditions=effective_conditions,
            egfr=effective_egfr,
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
            conditions=effective_conditions,
            egfr=effective_egfr,
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
            predicted = predict_unknown_interactions(drug_names, result["interactions"])
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
    """Derive the overall risk level from all findings.

    Scoring:
      - interactions: major=3, moderate=2, minor/unknown=1
      - Beers alerts: high=2, moderate/low=1
      - STOPP alerts: high=2, moderate/low=1
      - AI-predicted interactions: 1 each
      - START suggestions do not add risk (they flag missing therapy)
    Thresholds: >=12 HIGH, >=5 MODERATE, >=1 LOW, else MINIMAL.
    """
    score = 0

    for ix in result.get("interactions", []):
        sev = (ix.get("severity") or "").lower()
        score += _INTERACTION_WEIGHTS.get(sev, 1)

    for alert in result.get("beers_alerts", []):
        score += _ALERT_WEIGHTS.get((alert.get("severity") or "").lower(), 1)

    stopp_data = result.get("stopp_start", {})
    stopp_rules = stopp_data.get("stopp", []) if isinstance(stopp_data, dict) else []
    for rule in stopp_rules:
        score += _ALERT_WEIGHTS.get((rule.get("severity") or "").lower(), 1)

    score += len(result.get("predicted_interactions", [])) * _PREDICTED_WEIGHT

    result["risk_score"] = score

    if score >= _HIGH_THRESHOLD:
        return "HIGH"
    if score >= _MODERATE_THRESHOLD:
        return "MODERATE"
    if score > 0:
        return "LOW"
    return "MINIMAL"


def get_demo_cases() -> list[dict]:
    """Three pre-built clinically realistic demo cases for judges.

    Condition labels MUST match CONDITION_OPTIONS exactly — they pre-fill
    the UI multiselect.
    """
    return [
        {
            "name": "Case 1 — Mild (Hypertension + Diabetes)",
            "description": (
                "70-year-old with well-controlled hypertension and type 2 "
                "diabetes. Simple guideline-concordant regimen with no "
                "interactions — demonstrates that the system stays quiet for "
                "a low-risk patient instead of crying wolf. Tip: lower the "
                "eGFR to 25 and re-analyze to watch the renal safety rules "
                "(metformin, STOPP-E2) activate live."
            ),
            "medication_text": (
                "metformin 500mg twice daily\n"
                "lisinopril 10mg once daily\n"
                "amlodipine 5mg once daily"
            ),
            "patient_age": 70,
            "conditions": ["Hypertension", "Diabetes Type 2"],
            "expected_risk": "MINIMAL",
        },
        {
            "name": "Case 2 — Moderate (Polypharmacy + GI/CV Risk)",
            "description": (
                "78-year-old with osteoarthritis, GERD, hypertension, and "
                "depression. Triggers the NSAID + ACE-inhibitor interaction "
                "(acute kidney injury risk), the sertraline + ibuprofen "
                "combination (GI bleeding risk), and Beers/STOPP flags for "
                "long-term PPI use and chronic NSAID use in the elderly."
            ),
            "medication_text": (
                "omeprazole 20mg once daily\n"
                "ibuprofen 400mg three times daily\n"
                "lisinopril 20mg once daily\n"
                "sertraline 50mg once daily\n"
                "acetaminophen 500mg as needed"
            ),
            "patient_age": 78,
            "conditions": ["Osteoarthritis", "GERD", "Hypertension", "Depression"],
            "expected_risk": "MODERATE",
        },
        {
            "name": "Case 3 — Severe (High-Risk Polypharmacy)",
            "description": (
                "85-year-old with atrial fibrillation, anxiety, insomnia, "
                "chronic pain, and heart failure on 8 medications. Triggers: "
                "warfarin + amiodarone (major bleed risk, INR elevation), "
                "digoxin + amiodarone (digoxin toxicity), opioid + "
                "benzodiazepine (respiratory depression — FDA black box), "
                "≥3 CNS-active drugs, high anticholinergic burden, and "
                "multiple Beers/STOPP flags (benzodiazepine in the elderly, "
                "first-generation antihistamine, opioid without laxative)."
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
                "Atrial Fibrillation",
                "Anxiety",
                "Insomnia",
                "Chronic Pain",
                "Heart Failure",
            ],
            "expected_risk": "HIGH",
        },
    ]
