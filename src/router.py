"""Token-Efficient Routing Agent.

Implements a two-tier routing strategy:
  - LOW / MINIMAL risk → local deterministic engine only (0 LLM tokens spent)
  - MODERATE / HIGH risk → escalate to the Fireworks cloud model for synthesis

This reserves paid cloud inference for the cases that actually need it and
answers routine checks entirely offline. The cloud model is configurable via
``config.REPORT_MODEL``.
"""

import json
import logging
import os
import re
from collections.abc import AsyncGenerator

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


# Optional ordered preference list of model ids to try before REPORT_MODEL.
# Empty by default: previously this hard-coded Gemma ids that are NOT served by
# our Fireworks account, so every request emitted two 404s ("Model not found")
# before silently falling through. That produced misleading logs and wasted a
# round-trip per call for no benefit. Set REPORT_MODEL_FALLBACKS (comma-
# separated) if you have an account that genuinely serves other models.
_PREFERRED_MODELS = [
    m.strip() for m in os.getenv("REPORT_MODEL_FALLBACKS", "").split(",") if m.strip()
]
_working_model: str | None = None


def _candidate_models() -> list[str]:
    """Ordered models to try: known-good first, then any configured preferences."""
    ordered = ([_working_model] if _working_model else []) + [
        *_PREFERRED_MODELS,
        config.REPORT_MODEL,
    ]
    seen: set[str] = set()
    return [m for m in ordered if m and not (m in seen or seen.add(m))]


def _remember_working_model(model_id: str) -> None:
    global _working_model
    _working_model = model_id


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

    client = _fireworks_client()
    stream = None
    first_chunk = None
    last_error = None

    for model_id in _candidate_models():
        try:
            logger.info(f"Attempting clinical narrative stream with model: {model_id}")
            stream = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.35,
                max_tokens=config.REPORT_MAX_TOKENS,
                stream=True,
            )
            # Try to fetch the first chunk to ensure the model exists/is active
            first_chunk = next(stream)
            logger.info(f"Successfully started stream using model: {model_id}")
            _remember_working_model(model_id)
            break
        except Exception as e:
            logger.warning(f"Model {model_id} failed to stream: {e}")
            last_error = e
            stream = None

    if stream is None:
        yield f"\n\n[AI narrative generation encountered an error: {last_error}]"
        return

    # Yield first chunk content
    delta = first_chunk.choices[0].delta.content if first_chunk.choices else None
    if delta:
        yield delta

    # Yield remaining chunks
    for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta


def generate_alternatives(
    analysis_result: dict,
) -> list[dict]:
    """Use the Fireworks cloud model to generate structured JSON prescribing alternatives.

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
        'Return ONLY a valid JSON object of the form {"alternatives": [ ... ]}. '
        "Each array element must have these exact keys: "
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

    client = _fireworks_client()
    last_error = None

    for model_id in _candidate_models():
        try:
            logger.info(f"Attempting alternatives generation with model: {model_id}")
            extra: dict = {"response_format": {"type": "json_object"}} if config.REPORT_JSON_MODE else {}
            response = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=config.REPORT_MAX_TOKENS,
                **extra,
            )
            raw = (response.choices[0].message.content or "").strip()
            # Strip markdown code fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)
            # Accept either the object form {"alternatives": [...]} or a bare array.
            if isinstance(parsed, dict):
                alts = parsed.get("alternatives") or next(
                    (v for v in parsed.values() if isinstance(v, list)), []
                )
                if isinstance(alts, list):
                    logger.info(f"Successfully generated alternatives using model: {model_id}")
                    _remember_working_model(model_id)
                    return alts
            elif isinstance(parsed, list):
                logger.info(f"Successfully generated alternatives using model: {model_id}")
                _remember_working_model(model_id)
                return parsed
        except Exception as e:
            logger.warning(f"Model {model_id} failed to generate alternatives: {e}")
            last_error = e

    logger.error(f"All models failed for alternatives generation. Last error: {last_error}")
    return []
