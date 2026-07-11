"""Drug interaction checking engine for DrugLens.

Deterministic rules layer: pairwise DDI lookup, AGS Beers Criteria (2023),
and STOPP/START v3 screening, with combination-rule and eGFR-aware gating.

Rule files may carry these optional gating keys (AND semantics — every gate
present on a rule must pass for it to fire):

- ``combination_groups``: list of drug-name groups; fires only when EVERY
  group has at least one matched drug (e.g. opioid + benzodiazepine).
- ``min_matches``: fires only when >= N distinct drugs from ``drugs`` match
  (e.g. >=3 concurrent CNS-active drugs).
- ``egfr_below``: fires only when the patient's eGFR is known and below N.
- ``absent_drugs`` (STOPP): fires only when NONE of these are co-prescribed
  (e.g. opioid without laxative prophylaxis).
- ``conditions`` / ``min_age``: patient-condition and age gates.
"""

import json
from itertools import combinations
from pathlib import Path
from typing import Optional

import requests

DATA_DIR = Path(__file__).parent.parent / "data"

# ---------------------------------------------------------------------------
# Module-level caches
# ---------------------------------------------------------------------------
_interaction_db: list[dict] | None = None
_smiles_cache: dict[str, Optional[str]] = {}


def reset_caches() -> None:
    """Clear module caches (used by tests)."""
    global _interaction_db
    _interaction_db = None
    _smiles_cache.clear()


# ---------------------------------------------------------------------------
# Brand -> generic mappings
# ---------------------------------------------------------------------------
DRUG_ALIASES: dict[str, str] = {
    "tylenol": "acetaminophen",
    "paracetamol": "acetaminophen",
    "advil": "ibuprofen",
    "motrin": "ibuprofen",
    "aleve": "naproxen",
    "lipitor": "atorvastatin",
    "crestor": "rosuvastatin",
    "zocor": "simvastatin",
    "plavix": "clopidogrel",
    "coumadin": "warfarin",
    "jantoven": "warfarin",
    "xanax": "alprazolam",
    "valium": "diazepam",
    "ativan": "lorazepam",
    "klonopin": "clonazepam",
    "ambien": "zolpidem",
    "lunesta": "eszopiclone",
    "prilosec": "omeprazole",
    "nexium": "esomeprazole",
    "prevacid": "lansoprazole",
    "protonix": "pantoprazole",
    "zantac": "ranitidine",
    "pepcid": "famotidine",
    "glucophage": "metformin",
    "januvia": "sitagliptin",
    "lantus": "insulin glargine",
    "humalog": "insulin lispro",
    "novolog": "insulin aspart",
    "synthroid": "levothyroxine",
    "levoxyl": "levothyroxine",
    "norvasc": "amlodipine",
    "prinivil": "lisinopril",
    "zestril": "lisinopril",
    "vasotec": "enalapril",
    "altace": "ramipril",
    "diovan": "valsartan",
    "cozaar": "losartan",
    "lopressor": "metoprolol",
    "toprol": "metoprolol",
    "tenormin": "atenolol",
    "lasix": "furosemide",
    "bumex": "bumetanide",
    "hctz": "hydrochlorothiazide",
    "microzide": "hydrochlorothiazide",
    "prozac": "fluoxetine",
    "zoloft": "sertraline",
    "lexapro": "escitalopram",
    "celexa": "citalopram",
    "paxil": "paroxetine",
    "effexor": "venlafaxine",
    "cymbalta": "duloxetine",
    "wellbutrin": "bupropion",
    "seroquel": "quetiapine",
    "abilify": "aripiprazole",
    "risperdal": "risperidone",
    "zyprexa": "olanzapine",
    "neurontin": "gabapentin",
    "lyrica": "pregabalin",
    "tegretol": "carbamazepine",
    "dilantin": "phenytoin",
    "depakote": "valproic acid",
    "lamictal": "lamotrigine",
    "vicodin": "hydrocodone",
    # Combination products map to their opioid component; the acetaminophen
    # part is not tracked separately (accepted limitation).
    "percocet": "oxycodone",
    "oxycontin": "oxycodone",
    "celebrex": "celecoxib",
    "viagra": "sildenafil",
    "cialis": "tadalafil",
    "eliquis": "apixaban",
    "xarelto": "rivaroxaban",
    "pradaxa": "dabigatran",
    "benadryl": "diphenhydramine",
    "zyrtec": "cetirizine",
    "claritin": "loratadine",
    "allegra": "fexofenadine",
    "singulair": "montelukast",
    "flovent": "fluticasone",
    "ventolin": "albuterol",
    "proair": "albuterol",
    "spiriva": "tiotropium",
}

# ---------------------------------------------------------------------------
# Condition-vocabulary synonyms: UI labels <-> rule-data terms.
# expand_conditions() maps any member of a group to the whole group, so
# "Heart Failure" (UI), "chf" (clinical note) and "heart failure" (rule data)
# all intersect.
# ---------------------------------------------------------------------------
CONDITION_SYNONYM_GROUPS: list[frozenset[str]] = [
    frozenset({"diabetes type 2", "type 2 diabetes", "diabetes", "t2dm", "diabetes mellitus"}),
    frozenset({"heart failure", "chf", "congestive heart failure", "hfref"}),
    frozenset({"atrial fibrillation", "afib", "a-fib", "af"}),
    frozenset({"chronic kidney disease", "ckd", "renal impairment", "renal failure"}),
    frozenset({"gerd", "gastroesophageal reflux disease", "reflux", "acid reflux"}),
    frozenset({"dvt/pe", "dvt", "pe", "pulmonary embolism", "venous thromboembolism", "vte",
               "deep vein thrombosis"}),
    frozenset({"parkinson's disease", "parkinson", "parkinsons", "parkinson disease"}),
    frozenset({"coronary artery disease", "cad", "ischemic heart disease",
               "cardiovascular disease"}),
    frozenset({"peripheral artery disease", "pad", "peripheral vascular disease"}),
    frozenset({"stroke", "cva", "tia", "cerebrovascular disease"}),
    frozenset({"copd", "chronic obstructive pulmonary disease"}),
    frozenset({"depression", "major depression"}),
    frozenset({"chronic pain", "pain"}),
    frozenset({"epilepsy", "seizure", "seizure disorder"}),
    frozenset({"dementia", "alzheimer's disease", "cognitive impairment"}),
    frozenset({"gout", "hyperuricemia"}),
    frozenset({"osteoporosis", "fragility fracture"}),
    frozenset({"bph", "benign prostatic hyperplasia", "prostatism"}),
    frozenset({"falls", "fall risk", "history of falls"}),
    frozenset({"orthostatic hypotension", "postural hypotension"}),
    frozenset({"glaucoma", "narrow-angle glaucoma", "closed-angle glaucoma"}),
    frozenset({"constipation", "chronic constipation"}),
    frozenset({"peptic ulcer", "peptic ulcer disease", "gi bleeding"}),
    frozenset({"osteoarthritis", "oa"}),
]

_CONDITION_INDEX: dict[str, frozenset[str]] = {
    term: group for group in CONDITION_SYNONYM_GROUPS for term in group
}


def expand_conditions(conditions: list[str] | None) -> set[str]:
    """Lowercase each condition and expand it with its known synonyms."""
    expanded: set[str] = set()
    for cond in conditions or []:
        term = cond.strip().lower()
        if not term:
            continue
        expanded.add(term)
        expanded.update(_CONDITION_INDEX.get(term, frozenset()))
    return expanded


# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------
_SEVERITY_ORDER = {"major": 0, "moderate": 1, "minor": 2, "unknown": 3}


def normalize_drug_name(name: str) -> str:
    """Normalize drug name: lowercase, strip, resolve brand aliases."""
    cleaned = name.strip().lower()
    return DRUG_ALIASES.get(cleaned, cleaned)


def rxnorm_lookup(drug_name: str) -> Optional[dict]:
    """Query RxNorm API to get RxCUI and standardized name."""
    normalized = normalize_drug_name(drug_name)
    url = "https://rxnav.nlm.nih.gov/REST/rxcui.json"
    try:
        resp = requests.get(url, params={"name": normalized}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        id_group = data.get("idGroup", {})
        rxnorm_ids = id_group.get("rxnormId")
        if rxnorm_ids:
            return {"rxcui": rxnorm_ids[0], "name": id_group.get("name", normalized)}
    except (requests.RequestException, KeyError, json.JSONDecodeError):
        pass
    return None


def load_interaction_db() -> list[dict]:
    """Load drug_interactions.json from data dir. Cached after first call."""
    global _interaction_db
    if _interaction_db is not None:
        return _interaction_db

    db_path = DATA_DIR / "drug_interactions.json"
    if db_path.exists():
        with open(db_path, encoding="utf-8") as f:
            _interaction_db = json.load(f)
    else:
        _interaction_db = []
    return _interaction_db


def _load_json(filename: str, default: list | dict) -> list | dict:
    path = DATA_DIR / filename
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def check_interactions(medications: list[str]) -> list[dict]:
    """Check all pairs of medications against the interaction database.

    Returns interactions sorted by severity (major first). Each result:
    {drug_a, drug_b, severity, mechanism, effect, management,
    evidence_level, source}.
    """
    db = load_interaction_db()
    normalized = [normalize_drug_name(m) for m in medications]
    results: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    for a, b in combinations(normalized, 2):
        pair = tuple(sorted((a, b)))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        for entry in db:
            entry_a = entry.get("drug_a", "").lower()
            entry_b = entry.get("drug_b", "").lower()
            if (a == entry_a and b == entry_b) or (a == entry_b and b == entry_a):
                results.append({
                    "drug_a": a,
                    "drug_b": b,
                    "severity": entry.get("severity", "unknown"),
                    "mechanism": entry.get("mechanism", ""),
                    "effect": entry.get("effect", ""),
                    "management": entry.get("management", ""),
                    "evidence_level": entry.get("evidence_level", ""),
                    "source": "database",
                })
                break  # one alert per medication pair

    results.sort(key=lambda r: _SEVERITY_ORDER.get(r["severity"], 99))
    return results


def _rule_matches(rule: dict, normalized_meds: set[str]) -> list[str]:
    """Return the matched drugs if the rule's drug logic is satisfied, else [].

    ``combination_groups`` (all-groups semantics) takes precedence over the
    flat ``drugs`` list with its optional ``min_matches`` threshold.
    """
    groups = rule.get("combination_groups")
    if groups:
        matched: list[str] = []
        for group in groups:
            group_set = {g.lower() for g in group}
            hits = sorted(normalized_meds & group_set)
            if not hits:
                return []
            matched.extend(hits)
        return sorted(set(matched))

    flat = {d.lower() for d in rule.get("drugs", [])}
    matched = sorted(normalized_meds & flat)
    if len(matched) < rule.get("min_matches", 1):
        return []
    return matched


def _passes_patient_gates(
    rule: dict,
    patient_age: int,
    expanded_conditions: set[str],
    egfr: float | None,
) -> bool:
    """Apply age, condition, and eGFR gates shared by Beers and STOPP/START."""
    if patient_age < rule.get("min_age", 0):
        return False

    rule_conditions = {c.lower() for c in rule.get("conditions", [])}
    if rule_conditions and not (rule_conditions & expanded_conditions):
        return False

    egfr_below = rule.get("egfr_below")
    if egfr_below is not None and (egfr is None or egfr >= egfr_below):
        return False

    return True


def check_beers_criteria(
    medications: list[str],
    patient_age: int,
    conditions: list[str] | None = None,
    egfr: float | None = None,
) -> list[dict]:
    """Check medications against AGS Beers Criteria for adults >= 65.

    Each alert: {id, category, drug_class, matched_drugs, recommendation,
    rationale, severity, exceptions, quality_of_evidence}.
    """
    if patient_age < 65:
        return []

    criteria: list[dict] = _load_json("beers_criteria.json", [])
    normalized = {normalize_drug_name(m) for m in medications}
    expanded = expand_conditions(conditions)
    results: list[dict] = []

    for criterion in criteria:
        matched_drugs = _rule_matches(criterion, normalized)
        if not matched_drugs:
            continue
        if not _passes_patient_gates(criterion, patient_age, expanded, egfr):
            continue

        results.append({
            "id": criterion.get("id", ""),
            "category": criterion.get("category", ""),
            "drug_class": criterion.get("drug_class", ""),
            "matched_drugs": matched_drugs,
            "recommendation": criterion.get("recommendation", ""),
            "rationale": criterion.get("rationale", ""),
            "severity": criterion.get("severity", "moderate"),
            "exceptions": criterion.get("exceptions", ""),
            "quality_of_evidence": criterion.get("quality_of_evidence", ""),
        })

    return results


def check_stopp_start(
    medications: list[str],
    patient_age: int,
    conditions: list[str] | None = None,
    egfr: float | None = None,
) -> dict:
    """Check medications against STOPP/START criteria (geriatric, age >= 65).

    STOPP: drugs the patient IS taking that should be stopped.
    START: drugs the patient is NOT taking that should be started.
    """
    if patient_age < 65:
        return {"stopp": [], "start": []}

    criteria: dict = _load_json("stopp_start.json", {"stopp": [], "start": []})
    normalized = {normalize_drug_name(m) for m in medications}
    expanded = expand_conditions(conditions)
    stopp_results: list[dict] = []
    start_results: list[dict] = []

    for rule in criteria.get("stopp", []):
        matched = _rule_matches(rule, normalized)
        if not matched:
            continue
        if not _passes_patient_gates(rule, patient_age, expanded, egfr):
            continue

        # Absence gate: rule fires only when no protective co-prescription exists
        absent = {d.lower() for d in rule.get("absent_drugs", [])}
        if absent and (absent & normalized):
            continue

        stopp_results.append({
            "id": rule.get("id", ""),
            "section": rule.get("section", ""),
            "category": rule.get("category", ""),
            "criteria": rule.get("criteria", ""),
            "matched_drugs": matched,
            "rationale": rule.get("rationale", ""),
            "severity": rule.get("severity", "moderate"),
            "recommendation": rule.get("recommendation") or rule.get("criteria", ""),
        })

    for rule in criteria.get("start", []):
        # Rules without conditions apply universally (e.g. annual influenza
        # vaccine for all adults >= 65); otherwise require a condition match.
        rule_conditions = {c.lower() for c in rule.get("conditions", [])}
        conditions_matched = rule_conditions & expanded
        if rule_conditions and not conditions_matched:
            continue
        if not _passes_patient_gates(rule, patient_age, expanded, egfr):
            continue

        recommended_drugs = {d.lower() for d in rule.get("drugs", [])}
        # Trigger only if the patient is NOT already on a recommended drug
        if recommended_drugs & normalized:
            continue

        start_results.append({
            "id": rule.get("id", ""),
            "section": rule.get("section", ""),
            "category": rule.get("category", ""),
            "criteria": rule.get("criteria", ""),
            "recommended_drugs": sorted(recommended_drugs),
            "conditions_matched": sorted(conditions_matched),
            "rationale": rule.get("rationale", ""),
            "recommendation": rule.get("recommendation") or rule.get("criteria", ""),
        })

    return {"stopp": stopp_results, "start": start_results}


def get_drug_smiles(drug_name: str) -> Optional[str]:
    """Look up SMILES string for a drug via PubChem API. Results cached."""
    normalized = normalize_drug_name(drug_name)
    if normalized in _smiles_cache:
        return _smiles_cache[normalized]

    url = (
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
        f"{normalized}/property/CanonicalSMILES/JSON"
    )
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        props = data.get("PropertyTable", {}).get("Properties", [])
        if props:
            smiles = props[0].get("CanonicalSMILES")
            _smiles_cache[normalized] = smiles
            return smiles
    except (requests.RequestException, KeyError, json.JSONDecodeError):
        pass

    _smiles_cache[normalized] = None
    return None
