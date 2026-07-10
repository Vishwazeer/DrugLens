"""TxGemma-based drug-drug interaction predictor."""

import json
import os
import re
from itertools import combinations
from typing import Optional

from openai import OpenAI

from src.drug_interactions import get_drug_smiles, normalize_drug_name

TXGEMMA_BASE_URL = os.getenv("TXGEMMA_BASE_URL", "http://localhost:8002/v1")
TXGEMMA_MODEL = os.getenv("TXGEMMA_MODEL", "google/txgemma-2b-it")


def _txgemma_client() -> OpenAI:
    return OpenAI(base_url=TXGEMMA_BASE_URL, api_key="not-needed")


def _parse_json_response(raw: str) -> Optional[dict]:
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
) -> Optional[dict]:
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
            model=TXGEMMA_MODEL,
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
) -> Optional[dict]:
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
            model=TXGEMMA_MODEL,
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


def predict_unknown_interactions(
    medications: list[str], known_interactions: list[dict]
) -> list[dict]:
    """For drug pairs NOT already covered by known_interactions, use TxGemma.

    Limits to max 10 predictions to manage latency.
    """
    normalized = [normalize_drug_name(m) for m in medications]

    # Build set of known pairs for fast lookup
    known_pairs: set[tuple[str, str]] = set()
    for interaction in known_interactions:
        a = interaction.get("drug_a", "").lower()
        b = interaction.get("drug_b", "").lower()
        known_pairs.add(tuple(sorted((a, b))))

    # Find unknown pairs
    unknown_pairs: list[tuple[str, str]] = []
    for a, b in combinations(normalized, 2):
        pair = tuple(sorted((a, b)))
        if pair not in known_pairs:
            unknown_pairs.append((a, b))

    # Limit to 10
    unknown_pairs = unknown_pairs[:10]

    predictions: list[dict] = []
    for a, b in unknown_pairs:
        result = predict_ddi(a, b)
        if result:
            predictions.append(result)

    return predictions
