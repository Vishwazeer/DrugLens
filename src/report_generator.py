"""Risk report generator using Gemma 4 via Fireworks, with rule-based fallback."""

import json
import re

from openai import OpenAI

from src import config

# Covers both vocabularies: DDI severities (major/moderate/minor) and
# Beers/STOPP alert severities (high/moderate/low).
_SEVERITY_SCORE = {"major": 30, "high": 25, "moderate": 15, "minor": 5, "low": 5, "unknown": 10}


def _fireworks_client() -> OpenAI:
    return OpenAI(base_url=config.FIREWORKS_BASE_URL, api_key=config.FIREWORKS_API_KEY)


def _parse_json_response(raw: str) -> dict | None:
    """Best-effort JSON extraction from LLM output."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return None


def _build_context_block(
    medications: list[dict],
    interactions: list[dict],
    beers_alerts: list[dict],
    stopp_start: dict,
    predicted_ddis: list[dict],
    patient_info: dict,
) -> str:
    """Serialize all clinical data into a compact text block for the LLM."""
    sections: list[str] = []

    # Patient info
    pi_parts = []
    if patient_info.get("age"):
        pi_parts.append(f"Age: {patient_info['age']}")
    if patient_info.get("weight_kg"):
        pi_parts.append(f"Weight: {patient_info['weight_kg']} kg")
    if patient_info.get("egfr"):
        pi_parts.append(f"eGFR: {patient_info['egfr']}")
    if patient_info.get("conditions"):
        pi_parts.append(f"Conditions: {', '.join(patient_info['conditions'])}")
    if patient_info.get("allergies"):
        pi_parts.append(f"Allergies: {', '.join(patient_info['allergies'])}")
    if pi_parts:
        sections.append("PATIENT:\n" + "\n".join(pi_parts))

    # Medications
    med_lines = []
    for m in medications:
        parts = [m.get("name", "unknown")]
        if m.get("dose"):
            parts.append(m["dose"])
        if m.get("frequency"):
            parts.append(m["frequency"])
        if m.get("route"):
            parts.append(m["route"])
        med_lines.append(" ".join(parts))
    sections.append("MEDICATIONS:\n" + "\n".join(med_lines))

    # Interactions
    if interactions:
        ix_lines = []
        for ix in interactions:
            ix_lines.append(
                f"- [{ix.get('severity', '?').upper()}] {ix['drug_a']} + {ix['drug_b']}: "
                f"{ix.get('effect', '')}. {ix.get('management', '')}"
            )
        sections.append("KNOWN INTERACTIONS:\n" + "\n".join(ix_lines))

    # Beers
    if beers_alerts:
        ba_lines = []
        for ba in beers_alerts:
            drugs = ", ".join(ba.get("matched_drugs", []))
            ba_lines.append(
                f"- {drugs}: {ba.get('recommendation', '')} "
                f"(Rationale: {ba.get('rationale', '')})"
            )
        sections.append("BEERS CRITERIA ALERTS:\n" + "\n".join(ba_lines))

    # STOPP/START
    stopp_rules = stopp_start.get("stopp", [])
    start_rules = stopp_start.get("start", [])
    if stopp_rules:
        lines = [f"- {r.get('recommendation', '')}" for r in stopp_rules]
        sections.append("STOPP ALERTS (consider stopping):\n" + "\n".join(lines))
    if start_rules:
        lines = [f"- {r.get('recommendation', '')}" for r in start_rules]
        sections.append("START ALERTS (consider starting):\n" + "\n".join(lines))

    # Predicted DDIs
    if predicted_ddis:
        pd_lines = []
        for p in predicted_ddis:
            pd_lines.append(
                f"- {p['drug_a']} + {p['drug_b']}: "
                f"{p.get('predicted_interaction', '?')} "
                f"(confidence: {p.get('confidence', '?')})"
            )
        sections.append("AI-PREDICTED INTERACTIONS:\n" + "\n".join(pd_lines))

    return "\n\n".join(sections)


def _fallback_report(
    interactions: list[dict],
    beers_alerts: list[dict],
    stopp_start: dict,
) -> dict:
    """Generate a rule-based report without LLM access."""
    # Score calculation
    score = 0
    key_alerts: list[str] = []
    recommendations: list[str] = []

    for ix in interactions:
        sev = ix.get("severity", "unknown")
        score += _SEVERITY_SCORE.get(sev, 10)
        if sev == "major":
            key_alerts.append(
                f"MAJOR interaction: {ix['drug_a']} + {ix['drug_b']} — {ix.get('effect', '')}"
            )
            if ix.get("management"):
                recommendations.append(ix["management"])

    for ba in beers_alerts:
        sev = ba.get("severity", "moderate")
        score += _SEVERITY_SCORE.get(sev, 10)
        drugs = ", ".join(ba.get("matched_drugs", []))
        key_alerts.append(f"Beers Criteria: {drugs} — {ba.get('recommendation', '')}")

    stopp_rules = stopp_start.get("stopp", [])
    start_rules = stopp_start.get("start", [])

    for rule in stopp_rules:
        score += _SEVERITY_SCORE.get(rule.get("severity", "moderate"), 15)
        drugs = ", ".join(rule.get("matched_drugs", []))
        key_alerts.append(f"STOPP: {drugs} — {rule.get('recommendation', '')}")

    for rule in start_rules:
        score += 5
        drugs = ", ".join(rule.get("recommended_drugs", []))
        recommendations.append(
            f"Consider starting {drugs}: {rule.get('recommendation', '')}"
        )

    # Cap score at 100
    score = min(score, 100)

    if score >= 60:
        risk_level = "high"
    elif score >= 30:
        risk_level = "moderate"
    else:
        risk_level = "low"

    major_count = sum(1 for ix in interactions if ix.get("severity") == "major")
    moderate_count = sum(1 for ix in interactions if ix.get("severity") == "moderate")

    summary_parts = []
    if major_count:
        summary_parts.append(f"{major_count} major drug interaction(s)")
    if moderate_count:
        summary_parts.append(f"{moderate_count} moderate interaction(s)")
    if beers_alerts:
        summary_parts.append(f"{len(beers_alerts)} Beers Criteria alert(s)")
    if stopp_rules:
        summary_parts.append(f"{len(stopp_rules)} STOPP alert(s)")
    if start_rules:
        summary_parts.append(f"{len(start_rules)} START recommendation(s)")

    summary = (
        f"Risk level: {risk_level.upper()}. Found: {'; '.join(summary_parts)}."
        if summary_parts
        else "No significant issues identified."
    )

    return {
        "overall_risk_score": risk_level,
        "risk_score_numeric": score,
        "summary": summary,
        "clinical_summary": summary,
        "deprescribing_suggestions": [],
        "key_alerts": key_alerts[:10],
        "recommendations": recommendations[:10],
    }


def generate_risk_report(
    medications: list[dict],
    interactions: list[dict],
    beers_alerts: list[dict],
    stopp_start: dict,
    predicted_ddis: list[dict],
    patient_info: dict,
) -> dict:
    """Generate a comprehensive risk report via the Fireworks cloud model.

    Falls back to a rule-based report if the API is unavailable.
    """
    context = _build_context_block(
        medications, interactions, beers_alerts, stopp_start, predicted_ddis, patient_info
    )

    system_prompt = (
        "You are a clinical pharmacist AI generating a medication safety report.\n"
        "Analyze the clinical data and produce a JSON object with these keys:\n"
        '  "overall_risk_score": "high", "moderate", or "low",\n'
        '  "risk_score_numeric": integer 0-100,\n'
        '  "summary": patient-friendly summary (2-3 sentences, plain English),\n'
        '  "clinical_summary": detailed summary for healthcare providers,\n'
        '  "deprescribing_suggestions": [{drug, reason, alternative, priority}],\n'
        '  "key_alerts": list of the most critical findings (strings),\n'
        '  "recommendations": list of actionable recommendations (strings)\n'
        "Respond ONLY with the JSON object, no markdown fences, no extra text."
    )

    if not config.FIREWORKS_API_KEY:
        return _fallback_report(interactions, beers_alerts, stopp_start)

    try:
        client = _fireworks_client()
        # JSON mode forces a clean object from reasoning models that would
        # otherwise emit chain-of-thought before the JSON.
        extra: dict = {"response_format": {"type": "json_object"}} if config.REPORT_JSON_MODE else {}
        response = client.chat.completions.create(
            model=config.REPORT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context},
            ],
            temperature=0.3,
            # Headroom for reasoning models that emit hidden chain-of-thought
            # before the JSON — too small a budget truncates the report object.
            max_tokens=config.REPORT_MAX_TOKENS,
            **extra,
        )

        raw = response.choices[0].message.content or ""
        parsed = _parse_json_response(raw)
        if parsed and "overall_risk_score" in parsed:
            # Ensure all expected keys exist
            return {
                "overall_risk_score": parsed.get("overall_risk_score", "unknown"),
                "risk_score_numeric": parsed.get("risk_score_numeric", 0),
                "summary": parsed.get("summary", ""),
                "clinical_summary": parsed.get("clinical_summary", ""),
                "deprescribing_suggestions": parsed.get("deprescribing_suggestions", []),
                "key_alerts": parsed.get("key_alerts", []),
                "recommendations": parsed.get("recommendations", []),
            }
    except Exception:
        pass

    return _fallback_report(interactions, beers_alerts, stopp_start)


def generate_patient_summary(
    risk_report: dict,
    medications: list[dict],
) -> str:
    """Generate plain-English patient-friendly summary.

    Uses the Fireworks cloud model if available, otherwise builds from
    report data.
    """
    # Template fallback
    def _template_summary() -> str:
        med_names = [m.get("name", "unknown") for m in medications]
        risk = risk_report.get("overall_risk_score", "unknown")
        score = risk_report.get("risk_score_numeric", 0)
        alerts = risk_report.get("key_alerts", [])

        lines = [
            f"You are currently taking {len(med_names)} medication(s): {', '.join(med_names)}.",
            "",
            f"Your overall medication risk level is {risk.upper()} (score: {score}/100).",
        ]

        if alerts:
            lines.append("")
            lines.append("Important things to know:")
            for i, alert in enumerate(alerts[:5], 1):
                lines.append(f"  {i}. {alert}")

        recs = risk_report.get("recommendations", [])
        if recs:
            lines.append("")
            lines.append("What you can do:")
            for i, rec in enumerate(recs[:5], 1):
                lines.append(f"  {i}. {rec}")

        lines.append("")
        lines.append(
            "Please discuss these findings with your doctor or pharmacist "
            "before making any changes to your medications."
        )
        return "\n".join(lines)

    if not config.FIREWORKS_API_KEY:
        return _template_summary()

    context = (
        f"Medications: {json.dumps(medications)}\n"
        f"Risk report: {json.dumps(risk_report)}"
    )

    try:
        client = _fireworks_client()
        response = client.chat.completions.create(
            model=config.REPORT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a friendly pharmacist explaining medication safety to a patient. "
                        "Write a clear, easy-to-understand summary in plain English. "
                        "Avoid medical jargon. Be reassuring but honest about risks. "
                        "Keep it to 3-5 short paragraphs. "
                        "End by recommending they talk to their doctor."
                    ),
                },
                {"role": "user", "content": context},
            ],
            temperature=0.4,
            max_tokens=1024,
        )

        text = (response.choices[0].message.content or "").strip()
        if len(text) > 50:
            return text
    except Exception:
        pass

    return _template_summary()
