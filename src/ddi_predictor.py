"""TxGemma-based drug-drug interaction predictor."""

import json
import logging
import re
from itertools import combinations

from openai import OpenAI

from src import config
from src.drug_interactions import get_drug_smiles, normalize_drug_name

logger = logging.getLogger(__name__)


def _txgemma_client() -> OpenAI:
    return OpenAI(base_url=config.TXGEMMA_BASE_URL, api_key="not-needed")


def _parse_json_response(raw: str) -> dict | None:
    """Best-effort JSON extraction from LLM response."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to find first { ... }
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return None


def predict_ddi(
    drug_a: str,
    drug_b: str,
    smiles_a: str | None = None,
    smiles_b: str | None = None,
) -> dict | None:
    """Use TxGemma to predict drug-drug interaction between two drugs.

    If SMILES not provided, looks them up via PubChem.
    Returns {drug_a, drug_b, predicted_interaction, confidence, mechanism} or None.
    """
    name_a = normalize_drug_name(drug_a)
    name_b = normalize_drug_name(drug_b)

    if smiles_a is None:
        smiles_a = get_drug_smiles(name_a)
    if smiles_b is None:
        smiles_b = get_drug_smiles(name_b)

    # Build prompt with whatever info we have
    prompt_parts = [
        f"Predict the drug-drug interaction between {name_a} and {name_b}."
    ]
    if smiles_a:
        prompt_parts.append(f"SMILES for {name_a}: {smiles_a}")
    if smiles_b:
        prompt_parts.append(f"SMILES for {name_b}: {smiles_b}")

    prompt_parts.append(
        "\nRespond ONLY with a JSON object with these keys:\n"
        '  "predicted_interaction": brief description of the interaction or "none predicted",\n'
        '  "confidence": "high", "medium", or "low",\n'
        '  "mechanism": pharmacological mechanism of interaction or "unknown",\n'
        '  "severity": "major", "moderate", "minor", or "unknown",\n'
        '  "recommendation": clinical recommendation'
    )

    try:
        client = _txgemma_client()
        response = client.chat.completions.create(
            model=config.TXGEMMA_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are TxGemma, a therapeutic AI model. "
                        "Predict drug-drug interactions based on pharmacological knowledge. "
                        "Respond only with valid JSON."
                    ),
                },
                {"role": "user", "content": "\n".join(prompt_parts)},
            ],
            temperature=0.2,
            max_tokens=512,
        )

        raw = response.choices[0].message.content or ""
        parsed = _parse_json_response(raw)
        if parsed:
            return {
                "drug_a": name_a,
                "drug_b": name_b,
                "predicted_interaction": parsed.get("predicted_interaction", "unknown"),
                "confidence": parsed.get("confidence", "low"),
                "mechanism": parsed.get("mechanism", "unknown"),
                "severity": parsed.get("severity", "unknown"),
                "recommendation": parsed.get("recommendation", ""),
                "source": "txgemma_prediction",
            }
    except Exception:
        pass

    return None


def predict_toxicity(
    drug_name: str, smiles: str | None = None
) -> dict | None:
    """Use TxGemma to predict toxicity risk for a drug."""
    normalized = normalize_drug_name(drug_name)

    if smiles is None:
        smiles = get_drug_smiles(normalized)

    prompt_parts = [f"Predict the toxicity risk profile for {normalized}."]
    if smiles:
        prompt_parts.append(f"SMILES: {smiles}")

    prompt_parts.append(
        "\nRespond ONLY with a JSON object with these keys:\n"
        '  "toxicity_risk": "high", "moderate", or "low",\n'
        '  "mechanisms": list of toxicity mechanisms (e.g. ["hepatotoxicity", "nephrotoxicity"]),\n'
        '  "organ_systems": list of affected organ systems,\n'
        '  "monitoring": recommended monitoring parameters'
    )

    try:
        client = _txgemma_client()
        response = client.chat.completions.create(
            model=config.TXGEMMA_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are TxGemma, a therapeutic AI model. "
                        "Predict drug toxicity based on pharmacological knowledge. "
                        "Respond only with valid JSON."
                    ),
                },
                {"role": "user", "content": "\n".join(prompt_parts)},
            ],
            temperature=0.2,
            max_tokens=512,
        )

        raw = response.choices[0].message.content or ""
        parsed = _parse_json_response(raw)
        if parsed:
            return {
                "drug": normalized,
                "toxicity_risk": parsed.get("toxicity_risk", "unknown"),
                "mechanisms": parsed.get("mechanisms", []),
                "organ_systems": parsed.get("organ_systems", []),
                "monitoring": parsed.get("monitoring", ""),
                "source": "txgemma_prediction",
            }
    except Exception:
        pass

    return None


def _unknown_pairs(
    medications: list[str], known_interactions: list[dict], limit: int
) -> list[tuple[str, str]]:
    """Drug pairs that have NO entry in the curated interaction database.

    These are exactly the "novel drug blindspot" cases a lookup-table checker
    silently misses.
    """
    normalized = [normalize_drug_name(m) for m in medications]

    known_pairs: set[tuple[str, str]] = set()
    for interaction in known_interactions:
        a = interaction.get("drug_a", "").lower()
        b = interaction.get("drug_b", "").lower()
        known_pairs.add(tuple(sorted((a, b))))

    unknown: list[tuple[str, str]] = []
    for a, b in combinations(normalized, 2):
        if a == b:
            continue
        if tuple(sorted((a, b))) not in known_pairs:
            unknown.append((a, b))

    return unknown[:limit]


def predict_unknown_interactions(
    medications: list[str], known_interactions: list[dict]
) -> list[dict]:
    """For drug pairs NOT already covered by known_interactions, use TxGemma.

    Requires a local TxGemma vLLM server. Limits to 10 pairs for latency.
    """
    predictions: list[dict] = []
    for a, b in _unknown_pairs(medications, known_interactions, 10):
        result = predict_ddi(a, b)
        if result:
            predictions.append(result)
    return predictions


def predict_unknown_interactions_cloud(
    medications: list[str], known_interactions: list[dict], max_pairs: int = 12
) -> list[dict]:
    """Predict interactions for pairs absent from the curated database.

    This closes the "novel drug blindspot": a lookup table can only know the
    pairs someone already indexed. Here every *unindexed* pair is evaluated by
    the cloud model, grounded in each drug's molecular structure (PubChem
    SMILES) where available.

    All pairs go in a SINGLE batched call, so the cost is one request rather
    than one per pair.
    """
    if not config.FIREWORKS_API_KEY:
        return []

    pairs = _unknown_pairs(medications, known_interactions, max_pairs)
    if not pairs:
        return []

    # Ground the prediction in molecular structure where PubChem has it.
    # Best-effort: a lookup failure must never break the prediction.
    drugs = sorted({d for pair in pairs for d in pair})
    smiles: dict[str, str] = {}
    for drug in drugs:
        try:
            s = get_drug_smiles(drug)
            if s:
                smiles[drug] = s
        except Exception:  # noqa: BLE001 - structure is optional context
            pass

    structure_block = "\n".join(
        f"- {d}: {smiles[d]}" for d in drugs if d in smiles
    ) or "(structures unavailable)"
    pair_block = "\n".join(f"- {a} + {b}" for a, b in pairs)

    system_prompt = (
        "You are a clinical pharmacologist assessing drug-drug interactions that are "
        "NOT present in any curated interaction database. Reason from pharmacokinetics "
        "(CYP450 and P-glycoprotein effects, renal/hepatic clearance), pharmacodynamics "
        "(additive or opposing effects), and the molecular structures provided.\n"
        'Return ONLY a JSON object: {"predictions": [ ... ]}. Each element must have exactly: '
        '"drug_a" (string), "drug_b" (string), '
        '"predicted_interaction" (string; a concise clinical description, or "none expected"), '
        '"severity" ("major" | "moderate" | "minor" | "none"), '
        '"confidence" ("high" | "medium" | "low"), '
        '"mechanism" (string), "recommendation" (string).\n'
        "Be conservative: if there is no plausible interaction, say so with severity 'none'. "
        "Do NOT restate well-known interactions; these pairs are absent from our database."
    )

    user_prompt = (
        f"Patient medications: {', '.join(sorted({normalize_drug_name(m) for m in medications}))}\n\n"
        f"Molecular structures (SMILES):\n{structure_block}\n\n"
        f"Evaluate these UNINDEXED pairs:\n{pair_block}"
    )

    try:
        client = OpenAI(base_url=config.FIREWORKS_BASE_URL, api_key=config.FIREWORKS_API_KEY)
        extra: dict = {"response_format": {"type": "json_object"}} if config.REPORT_JSON_MODE else {}
        response = client.chat.completions.create(
            model=config.REPORT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=config.REPORT_MAX_TOKENS,
            **extra,
        )
        raw = (response.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)

        items = parsed.get("predictions") if isinstance(parsed, dict) else parsed
        if not isinstance(items, list):
            return []

        results: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity", "unknown")).lower()
            # Only surface genuine findings — reporting "no interaction" for every
            # pair would recreate the alert fatigue this project exists to fix.
            if severity in ("none", "", "unknown"):
                continue
            results.append({
                "drug_a": str(item.get("drug_a", "")).lower(),
                "drug_b": str(item.get("drug_b", "")).lower(),
                "predicted_interaction": item.get("predicted_interaction", ""),
                "severity": severity,
                "confidence": str(item.get("confidence", "low")).lower(),
                "mechanism": item.get("mechanism", ""),
                "recommendation": item.get("recommendation", ""),
                "smiles_used": bool(smiles.get(str(item.get("drug_a", "")).lower())
                                    and smiles.get(str(item.get("drug_b", "")).lower())),
                "source": "llm_prediction",
            })
        return results
    except Exception as e:  # noqa: BLE001
        logger.warning("Cloud novel-DDI prediction failed: %s", e)
        return []
