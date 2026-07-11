"""Medication parser: MedGemma LLM with regex fallback."""

import json
import re

from openai import OpenAI

from src import config

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Drug name: 1-3 words (letters/hyphens), not starting with a digit
_NAME_PAT = r"([a-zA-Z][a-zA-Z\-]+(?: [a-zA-Z\-]+){0,2})"

# Dose: number + optional space + unit
_DOSE_PAT = r"(\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|ml|mL|units?|iu|IU|meq|mEq))"

# Frequency aliases → normalized form
_FREQ_MAP: dict[str, str] = {
    "once daily": "once daily",
    "once a day": "once daily",
    "daily": "once daily",
    "qd": "once daily",
    "q.d.": "once daily",
    "qday": "once daily",
    "every day": "once daily",
    "od": "once daily",
    "twice daily": "twice daily",
    "twice a day": "twice daily",
    "bid": "twice daily",
    "b.i.d.": "twice daily",
    "2x daily": "twice daily",
    "two times a day": "twice daily",
    "three times daily": "three times daily",
    "three times a day": "three times daily",
    "tid": "three times daily",
    "t.i.d.": "three times daily",
    "3x daily": "three times daily",
    "four times daily": "four times daily",
    "four times a day": "four times daily",
    "qid": "four times daily",
    "q.i.d.": "four times daily",
    "4x daily": "four times daily",
    "every 4 hours": "every 4 hours",
    "q4h": "every 4 hours",
    "every 6 hours": "every 6 hours",
    "q6h": "every 6 hours",
    "every 8 hours": "every 8 hours",
    "q8h": "every 8 hours",
    "every 12 hours": "every 12 hours",
    "q12h": "every 12 hours",
    "every morning": "once daily (morning)",
    "every evening": "once daily (evening)",
    "every night": "once daily (bedtime)",
    "at bedtime": "once daily (bedtime)",
    "qhs": "once daily (bedtime)",
    "q.h.s.": "once daily (bedtime)",
    "weekly": "once weekly",
    "once weekly": "once weekly",
    "once a week": "once weekly",
    "as needed": "as needed",
    "prn": "as needed",
    "p.r.n.": "as needed",
}

# Build a single regex from frequency keys, longest first to avoid partial
# matches. Look-arounds (not \b — the dotted aliases like "q.d." break \b)
# stop short aliases such as "od"/"bid" matching inside drug names
# ("oxycodone", "carbidopa").
_freq_keys_sorted = sorted(_FREQ_MAP.keys(), key=len, reverse=True)
_FREQ_PAT = (
    r"(?<![A-Za-z0-9])("
    + "|".join(re.escape(k) for k in _freq_keys_sorted)
    + r")(?![A-Za-z0-9])"
)

# Route
_ROUTE_MAP: dict[str, str] = {
    "po": "oral",
    "p.o.": "oral",
    "oral": "oral",
    "by mouth": "oral",
    "orally": "oral",
    "iv": "intravenous",
    "i.v.": "intravenous",
    "intravenous": "intravenous",
    "im": "intramuscular",
    "i.m.": "intramuscular",
    "intramuscular": "intramuscular",
    "sq": "subcutaneous",
    "sc": "subcutaneous",
    "subq": "subcutaneous",
    "subcutaneous": "subcutaneous",
    "sl": "sublingual",
    "sublingual": "sublingual",
    "topical": "topical",
    "rectal": "rectal",
    "pr": "rectal",
    "inhaled": "inhaled",
    "inh": "inhaled",
    "nasal": "nasal",
    "ophthalmic": "ophthalmic",
    "otic": "otic",
    "transdermal": "transdermal",
    "patch": "transdermal",
}

_route_keys_sorted = sorted(_ROUTE_MAP.keys(), key=len, reverse=True)
_ROUTE_PAT = (
    r"(?<![A-Za-z0-9])("
    + "|".join(re.escape(k) for k in _route_keys_sorted)
    + r")(?![A-Za-z0-9])"
)


def parse_medications_llm(free_text: str) -> list[dict]:
    """Use MedGemma to parse free-text medication list into structured data."""
    client = OpenAI(base_url=config.MEDGEMMA_BASE_URL, api_key="not-needed")

    system_prompt = (
        "You are a clinical pharmacist. Extract every medication from the text below.\n"
        "Return ONLY a JSON array. Each element must have exactly these keys:\n"
        '  "name": generic drug name (lowercase),\n'
        '  "dose": dose with units (e.g. "500 mg") or null,\n'
        '  "frequency": how often taken (e.g. "twice daily") or null,\n'
        '  "route": route of administration (e.g. "oral") or null\n'
        "Do NOT include any text outside the JSON array."
    )

    response = client.chat.completions.create(
        model=config.MEDGEMMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": free_text},
        ],
        temperature=0.1,
        max_tokens=1024,
    )

    raw = response.choices[0].message.content or "[]"
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())

    parsed = json.loads(raw)
    if isinstance(parsed, list):
        return [
            {
                "name": item.get("name", ""),
                "dose": item.get("dose"),
                "frequency": item.get("frequency"),
                "route": item.get("route"),
            }
            for item in parsed
            if isinstance(item, dict) and item.get("name")
        ]
    return []


def parse_medications_regex(free_text: str) -> list[dict]:
    """Regex fallback parser for common prescription formats."""
    results: list[dict] = []
    # Split on newlines, semicolons, commas (but not commas inside dose like "1,000mg")
    lines = re.split(r"[;\n]+", free_text)
    # Further split on commas only if not part of a number
    expanded: list[str] = []
    for line in lines:
        parts = re.split(r",\s*(?![0-9])", line)
        expanded.extend(parts)

    for line in expanded:
        line = line.strip()
        if not line:
            continue

        entry: dict = {"name": "", "dose": None, "frequency": None, "route": None}

        # Extract dose
        dose_match = re.search(_DOSE_PAT, line, re.IGNORECASE)
        if dose_match:
            entry["dose"] = dose_match.group(1).strip()

        # Extract frequency (case-insensitive)
        freq_match = re.search(_FREQ_PAT, line, re.IGNORECASE)
        if freq_match:
            raw_freq = freq_match.group(1).lower()
            entry["frequency"] = _FREQ_MAP.get(raw_freq, raw_freq)

        # Extract route
        route_match = re.search(_ROUTE_PAT, line, re.IGNORECASE)
        if route_match:
            raw_route = route_match.group(1).lower()
            entry["route"] = _ROUTE_MAP.get(raw_route, raw_route)

        # Extract drug name: everything before the dose, or the first word(s)
        if dose_match:
            name_part = line[: dose_match.start()].strip()
        elif freq_match:
            name_part = line[: freq_match.start()].strip()
        else:
            name_part = line.strip()

        # Clean trailing/leading junk
        name_part = re.sub(r"^[\d\.\-\)\]\s]+", "", name_part)
        name_part = re.sub(r"[\s\-]+$", "", name_part)

        # Take only alphabetical words as the name
        name_words = re.findall(r"[a-zA-Z][a-zA-Z\-]+", name_part)
        if name_words:
            entry["name"] = " ".join(name_words).lower()
            results.append(entry)

    return results


def parse_medications(free_text: str, use_llm: bool = True) -> list[dict]:
    """Main entry point. Try LLM first, fall back to regex. Never throws."""
    if use_llm:
        try:
            result = parse_medications_llm(free_text)
            if result:
                return result
        except Exception:
            pass

    try:
        return parse_medications_regex(free_text)
    except Exception:
        return []


def extract_patient_info(free_text: str) -> dict:
    """Extract patient demographics and clinical info from free text."""
    info: dict = {
        "age": None,
        "weight_kg": None,
        "egfr": None,
        "conditions": [],
        "allergies": [],
    }

    # Age patterns
    age_patterns = [
        r"(?:age|aged)\s*:?\s*(\d{1,3})",
        r"(\d{1,3})\s*(?:year|yr|y/?o|years?)[\s\-]*old",
        r"(?:patient|pt).*?(\d{2,3})\s*(?:yo|y\.o\.)",
    ]
    for pat in age_patterns:
        m = re.search(pat, free_text, re.IGNORECASE)
        if m:
            age = int(m.group(1))
            if 0 < age < 130:
                info["age"] = age
                break

    # Weight patterns
    weight_patterns = [
        r"(?:weight|wt)\s*:?\s*(\d+(?:\.\d+)?)\s*kg",
        r"(\d+(?:\.\d+)?)\s*kg\b",
        r"(?:weight|wt)\s*:?\s*(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?)",
    ]
    for pat in weight_patterns:
        m = re.search(pat, free_text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            # Convert lbs to kg if the pattern matched pounds
            if "lb" in pat or "pound" in pat:
                val = round(val * 0.453592, 1)
            info["weight_kg"] = val
            break

    # eGFR
    egfr_match = re.search(
        r"(?:egfr|gfr|e-gfr)\s*:?\s*(\d+(?:\.\d+)?)", free_text, re.IGNORECASE
    )
    if egfr_match:
        info["egfr"] = float(egfr_match.group(1))

    # Conditions: look for common condition keywords
    condition_keywords = [
        "diabetes", "hypertension", "heart failure", "chf", "atrial fibrillation",
        "a-fib", "afib", "copd", "asthma", "ckd", "chronic kidney disease",
        "osteoporosis", "depression", "anxiety", "dementia", "parkinson",
        "epilepsy", "seizure", "gerd", "hypothyroidism", "hyperthyroidism",
        "dvt", "pe", "pulmonary embolism", "stroke", "cva", "tia",
        "osteoarthritis", "rheumatoid arthritis", "gout", "cirrhosis",
        "hepatitis", "cancer", "obesity", "bph", "glaucoma", "insomnia",
    ]
    text_lower = free_text.lower()
    for cond in condition_keywords:
        # Word-boundary match so short keywords like "pe" don't fire inside
        # "type", "pepcid", "percocet", etc.
        if re.search(rf"\b{re.escape(cond)}\b", text_lower):
            info["conditions"].append(cond)

    # Allergies: look for "allergic to X" or "allergies: X, Y"
    allergy_patterns = [
        r"allerg(?:y|ies|ic)\s*(?:to|:)\s*([^\n;\.]+)",
        r"(?:nkda|no known drug allergies)",
    ]
    for pat in allergy_patterns:
        m = re.search(pat, free_text, re.IGNORECASE)
        if m:
            if "nkda" in (m.group(0) or "").lower() or "no known" in (m.group(0) or "").lower():
                info["allergies"] = ["NKDA"]
            else:
                raw = m.group(1)
                info["allergies"] = [a.strip().lower() for a in re.split(r"[,;]+", raw) if a.strip()]
            break

    return info
