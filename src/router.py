"""Token-Efficient Routing Agent.

Implements a smart two-tier routing strategy:
  - LOW / MINIMAL risk → local deterministic engine only (0 tokens spent)
  - MODERATE / HIGH risk → escalate to Fireworks AI (Gemma 4) for deep analysis

This architecture maximises compute efficiency by reserving expensive GPU
inference (AMD Instinct MI300X via Fireworks AI) for the cases that actually
need it, while serving routine checks entirely offline in <50 ms.
"""

import json
import logging
import re
from typing import AsyncGenerator

from openai import OpenAI

from src import config

logger = logging.getLogger(__name__)

# Risk levels that warrant escalation to the LLM
_ESCALATION_LEVELS = {"HIGH", "MODERATE"}

# Routing decision labels surfaced to the UI
ROUTE_EDGE = "edge"          # deterministic engine only
ROUTE_CLOUD = "cloud_llm"   # escalated to Fireworks AI


def decide_route(risk_level: str) -> str:
    """Return ROUTE_EDGE or ROUTE_CLOUD based on computed risk level."""
    return ROUTE_CLOUD if risk_level in _ESCALATION_LEVELS else ROUTE_EDGE


def _fireworks_client() -> OpenAI:
    return OpenAI(base_url=config.FIREWORKS_BASE_URL, api_key=config.FIREWORKS_API_KEY)


def _build_stream_prompt(analysis_result: dict) -> tuple[str, str]:
    """Build system + user prompts for the streaming LLM call."""
    pi = analysis_result.get("patient_info", {})
    meds = [
        m.get("name") or m.get("drug_name") or m.get("raw", "")
        for m in analysis_result.get("parsed_medications", [])
    ]
    interactions = analysis_result.get("interactions", [])
    beers = analysis_result.get("beers_alerts", [])
    stopp = analysis_result.get("stopp_start", {}).get("stopp", [])
    start = analysis_result.get("stopp_start", {}).get("start", [])

    context_lines = [
        f"Patient: Age {pi.get('age', '?')}, eGFR {pi.get('egfr', 'unknown')}, "
        f"Conditions: {', '.join(pi.get('conditions', [])) or 'none'}",
        f"Medications ({len(meds)}): {', '.join(meds)}",
    ]

    if interactions:
        ix_strs = [
            f"[{ix.get('severity','?').upper()}] {ix.get('drug_a','')} + {ix.get('drug_b','')}: {ix.get('effect','')}"
            for ix in interactions[:6]
        ]
        context_lines.append("Known Interactions:\n" + "\n".join(ix_strs))

    if beers:
        b_strs = [
            f"{', '.join(b.get('matched_drugs', []))}: {b.get('recommendation', '')}"
            for b in beers[:4]
        ]
        context_lines.append("Beers Criteria:\n" + "\n".join(b_strs))

    if stopp:
        s_strs = [r.get("recommendation", "") for r in stopp[:4]]
        context_lines.append("STOPP Alerts:\n" + "\n".join(s_strs))

    if start:
        st_strs = [r.get("recommendation", "") for r in start[:3]]
        context_lines.append("START Suggestions:\n" + "\n".join(st_strs))

    system_prompt = (
        "You are a senior clinical pharmacist reviewing a high-risk polypharmacy case. "
        "Write a focused, actionable clinical narrative (3-5 paragraphs) for a prescribing physician. "
        "Be direct, specific, and prioritize patient safety. Mention the most dangerous interactions "
        "first. Suggest concrete alternatives or monitoring parameters where relevant. "
        "Do NOT use JSON. Write in flowing clinical prose."
    )

    user_prompt = "\n\n".join(context_lines) + f"\n\nOverall Risk: {analysis_result.get('risk_level', '?')} (Score: {analysis_result.get('risk_score', 0)})"

    return system_prompt, user_prompt


async def stream_clinical_narrative(
    analysis_result: dict,
) -> AsyncGenerator[str, None]:
    """Stream a Fireworks AI clinical narrative for HIGH/MODERATE cases.

    Yields raw text chunks as they arrive from the API (SSE-style).
    Falls back to a pre-built summary if the API is unavailable.
    """
    if not config.FIREWORKS_API_KEY:
        yield "AI narrative unavailable: no API key configured. The deterministic analysis above is complete."
        return

    system_prompt, user_prompt = _build_stream_prompt(analysis_result)

    try:
        client = _fireworks_client()
        stream = client.chat.completions.create(
            model=config.GEMMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.35,
            max_tokens=1024,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
    except Exception as e:
        logger.warning("Streaming LLM call failed: %s", e)
        yield f"\n\n[AI narrative generation encountered an error: {e}]"


def generate_alternatives(
    analysis_result: dict,
) -> list[dict]:
    """Use Fireworks AI (Gemma 4) to generate structured JSON prescribing alternatives.

    For each flagged drug, returns a list of dicts with:
      - drug: the flagged medication
      - reason: why it's flagged
      - safer_alternative: a specific safer drug name
      - rationale: why the alternative is safer for this patient
      - priority: 'high' | 'moderate'
    """
    if not config.FIREWORKS_API_KEY:
        return []

    pi = analysis_result.get("patient_info", {})
    meds = [
        m.get("name") or m.get("drug_name") or m.get("raw", "")
        for m in analysis_result.get("parsed_medications", [])
    ]
    flagged_drugs: dict[str, str] = {}

    for ix in analysis_result.get("interactions", []):
        if ix.get("severity") in ("major", "high"):
            a, b = ix.get("drug_a", ""), ix.get("drug_b", "")
            if a:
                flagged_drugs[a] = f"Major DDI with {b}: {ix.get('effect', '')}"
            if b:
                flagged_drugs[b] = f"Major DDI with {a}: {ix.get('effect', '')}"

    for alert in analysis_result.get("beers_alerts", []):
        for d in alert.get("matched_drugs", []):
            flagged_drugs[d] = f"Beers Criteria: {alert.get('recommendation', '')}"

    for rule in analysis_result.get("stopp_start", {}).get("stopp", []):
        for d in rule.get("matched_drugs", []):
            flagged_drugs[d] = f"STOPP: {rule.get('recommendation', '')}"

    if not flagged_drugs:
        return []

    # Limit to top 5 most problematic drugs
    flagged_list = list(flagged_drugs.items())[:5]
    flagged_text = "\n".join(f"- {drug}: {reason}" for drug, reason in flagged_list)

    system_prompt = (
        "You are a clinical pharmacist generating structured prescribing alternatives. "
        "Return ONLY a valid JSON array. Each element must have these exact keys: "
        '"drug" (string), "reason" (string), "safer_alternative" (string), '
        '"rationale" (string, max 20 words, specific to patient age/eGFR), '
        '"priority" (string, either "high" or "moderate"). '
        "Be specific and evidence-based. No markdown, no extra text."
    )

    user_prompt = (
        f"Patient: Age {pi.get('age', '?')}, eGFR {pi.get('egfr', 'not specified')}, "
        f"Conditions: {', '.join(pi.get('conditions', [])) or 'none specified'}.\n\n"
        f"Full medication list: {', '.join(meds)}.\n\n"
        f"Flagged drugs requiring alternatives:\n{flagged_text}\n\n"
        "Generate safer prescribing alternatives for each flagged drug."
    )

    try:
        client = _fireworks_client()
        response = client.chat.completions.create(
            model=config.GEMMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=1024,
        )
        raw = (response.choices[0].message.content or "").strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except Exception as e:
        logger.warning("Alternatives generation failed: %s", e)

    return []
