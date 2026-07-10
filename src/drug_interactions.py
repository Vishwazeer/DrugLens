"""Drug interaction checking engine for DrugLens."""

import json
import requests
from itertools import combinations
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"

# ---------------------------------------------------------------------------
# Module-level caches
# ---------------------------------------------------------------------------
_interaction_db: list[dict] | None = None
_smiles_cache: dict[str, Optional[str]] = {}

# ---------------------------------------------------------------------------
# 50+ common brand → generic mappings
# ---------------------------------------------------------------------------
DRUG_ALIASES: dict[str, str] = {
    "tylenol": "acetaminophen",
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
    "percocet": "oxycodone",
    "oxycontin": "oxycodone",
    "tramadol": "tramadol",
    "celebrex": "celecoxib",
    "viagra": "sildenafil",
    "cialis": "tadalafil",
    "eliquis": "apixaban",
    "xarelto": "rivarelbaan",
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
    "metformin": "metformin",
}

# Fix typo above
DRUG_ALIASES["xarelto"] = "rivaroxaban"

# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------
_SEVERITY_ORDER = {"major": 0, "moderate": 1, "minor": 2, "unknown": 3}


def normalize_drug_name(name: str) -> str:
    """Normalize drug name: lowercase, strip, resolve aliases."""
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
        with open(db_path, "r", encoding="utf-8") as f:
            _interaction_db = json.load(f)
    else:
        _interaction_db = []
    return _interaction_db


def check_interactions(medications: list[str]) -> list[dict]:
    """Check all pairs of medications against interaction database.

    Returns interactions sorted by severity (major first).
    Each result: {drug_a, drug_b, severity, mechanism, effect, management}.
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
                })

    results.sort(key=lambda r: _SEVERITY_ORDER.get(r["severity"], 99))
    return results


def check_beers_criteria(
    medications: list[str],
    patient_age: int,
    conditions: list[str] | None = None,
) -> list[dict]:
    """Check medications against Beers Criteria for older adults.

    Returns list of triggered criteria with recommendation, rationale, severity.
    """
    if patient_age < 65:
        return []

    beers_path = DATA_DIR / "beers_criteria.json"
    if beers_path.exists():
        with open(beers_path, "r", encoding="utf-8") as f:
            criteria = json.load(f)
    else:
        criteria = []

    normalized = [normalize_drug_name(m) for m in medications]
    conditions_lower = [c.lower() for c in (conditions or [])]
    results: list[dict] = []

    for criterion in criteria:
        # Drug-specific criteria
        criterion_drugs = [d.lower() for d in criterion.get("drugs", [])]
        matched_drugs = [d for d in normalized if d in criterion_drugs]

        if not matched_drugs:
            # Check drug class matching
            drug_classes = [c.lower() for c in criterion.get("drug_classes", [])]
            for d in normalized:
                for dc in drug_classes:
                    if dc in d or d in dc:
                        matched_drugs.append(d)

        if not matched_drugs:
            continue

        # Condition-dependent check
        required_conditions = [c.lower() for c in criterion.get("conditions", [])]
        if required_conditions and not any(
            rc in " ".join(conditions_lower) for rc in required_conditions
        ):
            continue

        results.append({
            "criterion_id": criterion.get("id", ""),
            "category": criterion.get("category", ""),
            "drugs_matched": matched_drugs,
            "recommendation": criterion.get("recommendation", ""),
            "rationale": criterion.get("rationale", ""),
            "severity": criterion.get("severity", "moderate"),
            "quality_of_evidence": criterion.get("quality_of_evidence", ""),
        })

    # Check for ≥3 CNS-active drugs
    cns_drugs_list = {
        "alprazolam", "lorazepam", "diazepam", "clonazepam", "zolpidem",
        "eszopiclone", "gabapentin", "pregabalin", "quetiapine", "olanzapine",
        "risperidone", "aripiprazole", "oxycodone", "hydrocodone", "tramadol",
        "amitriptyline", "nortriptyline", "doxepin", "diphenhydramine",
    }
    cns_matched = [d for d in normalized if d in cns_drugs_list]
    if len(cns_matched) >= 3:
        results.append({
            "criterion_id": "BEERS-CNS-POLY",
            "category": "Drug-Drug Interaction",
            "drugs_matched": cns_matched,
            "recommendation": "Avoid use of ≥3 CNS-active drugs concurrently",
            "rationale": "Increased risk of falls, fractures, cognitive impairment",
            "severity": "major",
            "quality_of_evidence": "High",
        })

    return results


def check_stopp_start(
    medications: list[str],
    patient_age: int,
    conditions: list[str] | None = None,
) -> dict:
    """Check medications against STOPP/START criteria.

    STOPP: drugs the patient IS taking that should be stopped.
    START: drugs the patient is NOT taking that should be started.
    """
    stopp_path = DATA_DIR / "stopp_start.json"
    if stopp_path.exists():
        with open(stopp_path, "r", encoding="utf-8") as f:
            criteria = json.load(f)
    else:
        criteria = {"stopp": [], "start": []}

    normalized = set(normalize_drug_name(m) for m in medications)
    conditions_lower = set(c.lower() for c in (conditions or []))
    stopp_results: list[dict] = []
    start_results: list[dict] = []

    # STOPP: drugs patient is taking that should be stopped
    for rule in criteria.get("stopp", []):
        rule_drugs = set(d.lower() for d in rule.get("drugs", []))
        matched = normalized & rule_drugs
        if not matched:
            continue

        # Check if age condition applies
        min_age = rule.get("min_age", 0)
        if patient_age < min_age:
            continue

        # Check condition requirements
        rule_conditions = set(c.lower() for c in rule.get("conditions", []))
        if rule_conditions and not (rule_conditions & conditions_lower):
            continue

        stopp_results.append({
            "rule_id": rule.get("id", ""),
            "category": rule.get("category", ""),
            "drugs_matched": list(matched),
            "recommendation": rule.get("recommendation", ""),
            "rationale": rule.get("rationale", ""),
            "evidence": rule.get("evidence", ""),
        })

    # START: drugs patient should be taking but isn't
    for rule in criteria.get("start", []):
        rule_conditions = set(c.lower() for c in rule.get("conditions", []))
        if not rule_conditions:
            continue
        if not (rule_conditions & conditions_lower):
            continue

        min_age = rule.get("min_age", 0)
        if patient_age < min_age:
            continue

        recommended_drugs = set(d.lower() for d in rule.get("drugs", []))
        # Trigger only if patient is NOT already on the recommended drug
        if not (recommended_drugs & normalized):
            start_results.append({
                "rule_id": rule.get("id", ""),
                "category": rule.get("category", ""),
                "recommended_drugs": list(recommended_drugs),
                "conditions_matched": list(rule_conditions & conditions_lower),
                "recommendation": rule.get("recommendation", ""),
                "rationale": rule.get("rationale", ""),
                "evidence": rule.get("evidence", ""),
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
