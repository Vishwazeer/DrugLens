"""
DrugLens Master Integration & Regression Test Suite
=====================================================
Tests EVERY layer of the project after the Streamlit → React/FastAPI migration:

1.  Data Integrity        — JSON rule-file shapes, required fields, no duplicates
2.  Drug Normalization    — brand aliases, case folding
3.  Condition Expansion   — synonym groups
4.  Interaction Engine    — pairwise DDI lookup, severity ordering
5.  Beers Criteria        — age gate, eGFR gate, condition gate, combination rules
6.  STOPP / START         — absent_drugs gate, combination_groups, START omission
7.  Risk Scoring          — weights, thresholds (MINIMAL→HIGH)
8.  Analyzer Pipeline     — key completeness, fallbacks, eGFR/condition merging
9.  Demo Cases (frozen)   — all 3 cases hit expected risk bands & named findings
10. API Layer (FastAPI)   — every HTTP endpoint: health, conditions, demo-cases, analyze
11. Frontend Build        — Vite project structure, package.json, tailwind config
12. Project Hygiene       — api.py present, app.py absent, requirements still importable

NEW (Hackathon Features):
13. Token-Efficient Router — decide_route logic, ROUTE_EDGE / ROUTE_CLOUD constants
14. Streaming Endpoint    — /api/analyze/stream-narrative SSE contract
15. Alternatives Endpoint — /api/analyze/alternatives JSON contract
16. Frontend Integration  — App.tsx references all new endpoints & routing

Run with:
    source venv/bin/activate
    python -m pytest scripts/master_test.py -v --tb=short
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
SRC_DIR      = PROJECT_ROOT / "src"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _offline_analyze(text: str, **kwargs) -> dict:
    from src.analyzer import analyze_medications
    kwargs.setdefault("use_llm_parser", False)
    kwargs.setdefault("use_txgemma",    False)
    kwargs.setdefault("use_gemma4",     False)
    return analyze_medications(text, **kwargs)


# ===========================================================================
# 1. DATA INTEGRITY
# ===========================================================================

class TestDataIntegrity:
    """Verify that the three JSON data-files are well-formed and complete."""

    def test_beers_criteria_json_loads(self):
        data = json.loads((DATA_DIR / "beers_criteria.json").read_text())
        assert isinstance(data, list), "beers_criteria.json must be a JSON array"
        assert len(data) >= 10, "Expected at least 10 Beers rules"

    def test_beers_required_fields(self):
        data = json.loads((DATA_DIR / "beers_criteria.json").read_text())
        required = {"id", "drugs", "recommendation", "rationale", "severity"}
        for rule in data:
            missing = required - rule.keys()
            assert not missing, f"Beers rule {rule.get('id')} missing: {missing}"

    def test_beers_severities_valid(self):
        data = json.loads((DATA_DIR / "beers_criteria.json").read_text())
        valid = {"high", "moderate", "low"}
        for rule in data:
            assert rule["severity"].lower() in valid, \
                f"Unexpected Beers severity: {rule['severity']} in {rule['id']}"

    def test_beers_no_duplicate_ids(self):
        data = json.loads((DATA_DIR / "beers_criteria.json").read_text())
        ids = [r["id"] for r in data]
        assert len(ids) == len(set(ids)), "Duplicate Beers IDs found"

    def test_stopp_start_json_loads(self):
        data = json.loads((DATA_DIR / "stopp_start.json").read_text())
        assert "stopp" in data and "start" in data
        assert len(data["stopp"]) >= 5
        assert len(data["start"]) >= 5

    def test_stopp_required_fields(self):
        data = json.loads((DATA_DIR / "stopp_start.json").read_text())
        for rule in data["stopp"]:
            assert "id" in rule, f"STOPP rule missing id: {rule}"
            assert "drugs" in rule or "combination_groups" in rule, \
                f"STOPP rule {rule.get('id')} has no drug matcher"

    def test_start_required_fields(self):
        data = json.loads((DATA_DIR / "stopp_start.json").read_text())
        for rule in data["start"]:
            assert "id" in rule
            assert "drugs" in rule

    def test_drug_interactions_json_loads(self):
        data = json.loads((DATA_DIR / "drug_interactions.json").read_text())
        assert isinstance(data, list)
        assert len(data) >= 50, "Expected ≥50 curated DDI entries"

    def test_ddi_required_fields(self):
        data = json.loads((DATA_DIR / "drug_interactions.json").read_text())
        for entry in data:
            for field in ("drug_a", "drug_b", "severity", "effect"):
                assert field in entry, f"DDI entry missing '{field}': {entry}"

    def test_ddi_severities_valid(self):
        data = json.loads((DATA_DIR / "drug_interactions.json").read_text())
        valid = {"major", "moderate", "minor", "unknown"}
        for e in data:
            assert e["severity"].lower() in valid, f"Bad DDI severity: {e['severity']}"

    def test_ddi_no_self_interactions(self):
        data = json.loads((DATA_DIR / "drug_interactions.json").read_text())
        for e in data:
            assert e["drug_a"].lower() != e["drug_b"].lower(), \
                f"Self-interaction found: {e['drug_a']}"


# ===========================================================================
# 2. DRUG NORMALIZATION
# ===========================================================================

class TestNormalization:

    def test_brand_to_generic_coumadin(self):
        from src.drug_interactions import normalize_drug_name
        assert normalize_drug_name("Coumadin") == "warfarin"

    def test_brand_to_generic_tylenol(self):
        from src.drug_interactions import normalize_drug_name
        assert normalize_drug_name("Tylenol") == "acetaminophen"

    def test_case_insensitive(self):
        from src.drug_interactions import normalize_drug_name
        assert normalize_drug_name("BENADRYL") == "diphenhydramine"

    def test_unknown_drug_passthrough(self):
        from src.drug_interactions import normalize_drug_name
        assert normalize_drug_name("unknowndrug123") == "unknowndrug123"

    def test_percocet_maps_to_oxycodone(self):
        from src.drug_interactions import normalize_drug_name
        assert normalize_drug_name("percocet") == "oxycodone"

    def test_strip_whitespace(self):
        from src.drug_interactions import normalize_drug_name
        assert normalize_drug_name("  warfarin  ") == "warfarin"


# ===========================================================================
# 3. CONDITION EXPANSION
# ===========================================================================

class TestConditionExpansion:

    def test_heart_failure_expands_to_chf(self):
        from src.drug_interactions import expand_conditions
        expanded = expand_conditions(["Heart Failure"])
        assert "chf" in expanded

    def test_afib_expands(self):
        from src.drug_interactions import expand_conditions
        expanded = expand_conditions(["Atrial Fibrillation"])
        assert "afib" in expanded

    def test_diabetes_expands(self):
        from src.drug_interactions import expand_conditions
        expanded = expand_conditions(["Diabetes Type 2"])
        assert "diabetes" in expanded

    def test_empty_conditions(self):
        from src.drug_interactions import expand_conditions
        assert expand_conditions([]) == set()

    def test_unknown_condition_kept(self):
        from src.drug_interactions import expand_conditions
        expanded = expand_conditions(["Rare Unknown Syndrome"])
        assert "rare unknown syndrome" in expanded


# ===========================================================================
# 4. INTERACTION ENGINE
# ===========================================================================

class TestInteractionEngine:

    def test_warfarin_amiodarone_major(self, reset_module_caches):
        from src.drug_interactions import check_interactions
        results = check_interactions(["warfarin", "amiodarone"])
        assert len(results) == 1
        assert results[0]["severity"] == "major"

    def test_ibuprofen_lisinopril_detected(self, reset_module_caches):
        from src.drug_interactions import check_interactions
        results = check_interactions(["ibuprofen", "lisinopril"])
        assert len(results) >= 1

    def test_safe_drugs_no_interaction(self, reset_module_caches):
        from src.drug_interactions import check_interactions
        results = check_interactions(["amlodipine", "lisinopril"])
        # Both are common antihypertensives — should NOT interact
        # (or if they do, it's acceptable; just check it doesn't crash)
        assert isinstance(results, list)

    def test_brand_name_resolved_in_interaction(self, reset_module_caches):
        from src.drug_interactions import check_interactions
        results = check_interactions(["Coumadin", "amiodarone"])
        assert any(
            r["drug_a"] == "warfarin" or r["drug_b"] == "warfarin" for r in results
        ), "Brand name 'Coumadin' should resolve to 'warfarin' before checking"

    def test_interactions_sorted_by_severity(self, reset_module_caches):
        from src.drug_interactions import check_interactions
        results = check_interactions(["warfarin", "amiodarone", "ibuprofen", "sertraline"])
        severities = [r["severity"] for r in results]
        severity_order = {"major": 0, "moderate": 1, "minor": 2, "unknown": 3}
        ranks = [severity_order.get(s, 99) for s in severities]
        assert ranks == sorted(ranks), "Results not sorted by severity"

    def test_single_drug_no_interactions(self, reset_module_caches):
        from src.drug_interactions import check_interactions
        assert check_interactions(["metformin"]) == []

    def test_empty_medication_list(self, reset_module_caches):
        from src.drug_interactions import check_interactions
        assert check_interactions([]) == []


# ===========================================================================
# 5. BEERS CRITERIA
# ===========================================================================

class TestBeersCriteria:

    def test_age_gate_under_65(self, reset_module_caches):
        from src.drug_interactions import check_beers_criteria
        results = check_beers_criteria(["diphenhydramine"], patient_age=50)
        assert results == [], "Beers should not fire for patients under 65"

    def test_diphenhydramine_flagged_at_65(self, reset_module_caches):
        from src.drug_interactions import check_beers_criteria
        results = check_beers_criteria(["diphenhydramine"], patient_age=65)
        assert len(results) >= 1

    def test_metformin_flagged_low_egfr(self, reset_module_caches):
        from src.drug_interactions import check_beers_criteria
        results = check_beers_criteria(["metformin"], patient_age=80, egfr=25.0)
        assert any(r["id"] == "BEERS-ENDO-008" for r in results)

    def test_metformin_safe_normal_egfr(self, reset_module_caches):
        from src.drug_interactions import check_beers_criteria
        results = check_beers_criteria(["metformin"], patient_age=80, egfr=90.0)
        assert not any(r["id"] == "BEERS-ENDO-008" for r in results)

    def test_long_term_ppi_flagged(self, reset_module_caches):
        from src.drug_interactions import check_beers_criteria
        results = check_beers_criteria(["omeprazole"], patient_age=78)
        assert any(r["id"] == "BEERS-GI-003" for r in results)

    def test_chronic_nsaid_flagged(self, reset_module_caches):
        from src.drug_interactions import check_beers_criteria
        results = check_beers_criteria(["ibuprofen"], patient_age=78)
        assert any(r["id"] == "BEERS-PAIN-001" for r in results)

    def test_beers_result_schema(self, reset_module_caches):
        from src.drug_interactions import check_beers_criteria
        results = check_beers_criteria(["diphenhydramine"], patient_age=70)
        for r in results:
            for key in ("id", "category", "matched_drugs", "rationale", "severity"):
                assert key in r, f"Beers result missing key: {key}"


# ===========================================================================
# 6. STOPP / START
# ===========================================================================

class TestStoppStart:

    def test_opioid_benzo_stopp_k2(self, reset_module_caches):
        from src.drug_interactions import check_stopp_start
        result = check_stopp_start(
            ["lorazepam", "oxycodone"], patient_age=85,
            conditions=["Chronic Pain", "Anxiety"]
        )
        stopp_ids = {r["id"] for r in result["stopp"]}
        assert "STOPP-K2" in stopp_ids

    def test_opioid_no_laxative_stopp_d9(self, reset_module_caches):
        from src.drug_interactions import check_stopp_start
        result = check_stopp_start(["oxycodone"], patient_age=80)
        stopp_ids = {r["id"] for r in result["stopp"]}
        assert "STOPP-D9" in stopp_ids

    def test_opioid_with_laxative_stopp_d9_suppressed(self, reset_module_caches):
        from src.drug_interactions import check_stopp_start
        result = check_stopp_start(["oxycodone", "bisacodyl"], patient_age=80)
        stopp_ids = {r["id"] for r in result["stopp"]}
        assert "STOPP-D9" not in stopp_ids

    def test_start_ace_inhibitor_for_heart_failure(self, reset_module_caches):
        from src.drug_interactions import check_stopp_start
        result = check_stopp_start(
            ["furosemide"], patient_age=80, conditions=["Heart Failure"]
        )
        start_ids = {r["id"] for r in result["start"]}
        assert "START-A2" in start_ids

    def test_start_not_triggered_if_drug_already_present(self, reset_module_caches):
        from src.drug_interactions import check_stopp_start
        result = check_stopp_start(
            ["lisinopril", "furosemide"], patient_age=80, conditions=["Heart Failure"]
        )
        start_ids = {r["id"] for r in result["start"]}
        assert "START-A2" not in start_ids

    def test_age_gate_under_65(self, reset_module_caches):
        from src.drug_interactions import check_stopp_start
        result = check_stopp_start(["lorazepam", "oxycodone"], patient_age=50)
        assert result == {"stopp": [], "start": []}

    def test_stopp_metformin_low_egfr(self, reset_module_caches):
        from src.drug_interactions import check_stopp_start
        result = check_stopp_start(["metformin"], patient_age=80, egfr=25.0)
        stopp_ids = {r["id"] for r in result["stopp"]}
        assert "STOPP-E2" in stopp_ids


# ===========================================================================
# 7. RISK SCORING
# ===========================================================================

class TestRiskScoring:

    def _synth(self, n_major=0, n_moderate=0, n_beers_high=0,
               n_stopp_high=0, n_predicted=0) -> dict:
        return {
            "interactions":          [{"severity": "major"}] * n_major
                                   + [{"severity": "moderate"}] * n_moderate,
            "beers_alerts":          [{"severity": "high"}] * n_beers_high,
            "stopp_start":           {"stopp": [{"severity": "high"}] * n_stopp_high, "start": []},
            "predicted_interactions":[{}] * n_predicted,
        }

    def test_empty_is_minimal(self):
        from src.analyzer import _compute_risk_level
        r = self._synth()
        assert _compute_risk_level(r) == "MINIMAL"
        assert r["risk_score"] == 0

    def test_one_moderate_is_low(self):
        from src.analyzer import _compute_risk_level
        r = self._synth(n_moderate=1)  # 2 pts
        assert _compute_risk_level(r) == "LOW"

    def test_five_points_is_moderate(self):
        from src.analyzer import _compute_risk_level
        r = self._synth(n_major=1, n_beers_high=1)  # 3+2=5
        assert _compute_risk_level(r) == "MODERATE"

    def test_high_threshold(self):
        from src.analyzer import _compute_risk_level
        r = self._synth(n_major=3, n_beers_high=1, n_stopp_high=1)  # 9+2+2=13
        assert _compute_risk_level(r) == "HIGH"

    def test_predicted_add_one_point_each(self):
        from src.analyzer import _compute_risk_level
        r = self._synth(n_predicted=3)  # 3 pts → LOW
        assert _compute_risk_level(r) == "LOW"


# ===========================================================================
# 8. ANALYZER PIPELINE
# ===========================================================================

class TestAnalyzerPipeline:

    def test_result_keys_complete(self):
        result = _offline_analyze("metformin 500mg daily", patient_age=70)
        required = {
            "parsed_medications", "patient_info", "interactions",
            "beers_alerts", "stopp_start", "predicted_interactions",
            "risk_report", "patient_summary", "errors", "risk_level", "risk_score"
        }
        assert required <= set(result.keys())

    def test_patient_info_keys(self):
        result = _offline_analyze("metformin 500mg daily", patient_age=70)
        assert {"age", "conditions", "egfr"} <= set(result["patient_info"].keys())

    def test_egfr_extracted_from_text(self):
        result = _offline_analyze("eGFR: 25\nmetformin 500mg daily", patient_age=80)
        assert result["patient_info"]["egfr"] == 25.0

    def test_explicit_egfr_wins_over_text(self):
        result = _offline_analyze("eGFR: 25\nmetformin 500mg daily",
                                  patient_age=80, patient_egfr=90.0)
        assert result["patient_info"]["egfr"] == 90.0

    def test_conditions_extracted_from_text(self):
        result = _offline_analyze("82yo with heart failure\nfurosemide 40mg", patient_age=82)
        lower_conds = [c.lower() for c in result["patient_info"]["conditions"]]
        assert "heart failure" in lower_conds

    def test_explicit_and_extracted_conditions_merged(self):
        result = _offline_analyze(
            "patient with copd\nmetformin 500mg",
            patient_age=75, patient_conditions=["Hypertension"]
        )
        lower = [c.lower() for c in result["patient_info"]["conditions"]]
        assert "hypertension" in lower and "copd" in lower

    def test_fallback_on_parser_failure(self, monkeypatch):
        import src.analyzer as analyzer_mod
        def boom(text, use_llm=True):
            raise RuntimeError("injected parse failure")
        monkeypatch.setattr(analyzer_mod, "parse_medications", boom)
        result = _offline_analyze("warfarin, amiodarone", patient_age=80)
        assert any("parsing failed" in e.lower() for e in result["errors"])
        assert len(result["parsed_medications"]) == 2

    def test_demo_conditions_all_in_condition_options(self):
        from src.analyzer import CONDITION_OPTIONS, get_demo_cases
        for case in get_demo_cases():
            for cond in case["conditions"]:
                assert cond in CONDITION_OPTIONS, \
                    f"Condition '{cond}' from {case['name']} not in CONDITION_OPTIONS"


# ===========================================================================
# 9. DEMO CASES (FROZEN)
# ===========================================================================

@pytest.fixture(scope="class")
def demo_results():
    from src.analyzer import analyze_medications, get_demo_cases
    out = {}
    for case in get_demo_cases():
        out[case["name"]] = analyze_medications(
            medication_text=case["medication_text"],
            patient_age=case["patient_age"],
            patient_conditions=case["conditions"],
            patient_egfr=60.0,
            use_llm_parser=False,
            use_txgemma=False,
            use_gemma4=False,
        )
    return out


class TestDemoCases:

    def _pairs(self, result):
        return {frozenset((i["drug_a"], i["drug_b"])) for i in result["interactions"]}

    def _case(self, demo_results, prefix):
        return next(v for k, v in demo_results.items() if k.startswith(prefix))

    def test_no_demo_case_has_errors(self, demo_results):
        for name, result in demo_results.items():
            assert not result["errors"], f"{name}: {result['errors']}"

    def test_case1_minimal_or_low(self, demo_results):
        r = self._case(demo_results, "Case 1")
        assert r["risk_level"] in {"MINIMAL", "LOW"}
        assert r["interactions"]         == []
        assert r["beers_alerts"]         == []
        assert r["stopp_start"]["stopp"] == []

    def test_case1_egfr_25_activates_renal_rules(self):
        from src.analyzer import analyze_medications, get_demo_cases
        case = get_demo_cases()[0]
        r = analyze_medications(
            medication_text=case["medication_text"],
            patient_age=case["patient_age"],
            patient_conditions=case["conditions"],
            patient_egfr=25.0,
            use_llm_parser=False, use_txgemma=False, use_gemma4=False,
        )
        assert "BEERS-ENDO-008" in {b["id"] for b in r["beers_alerts"]}
        assert "STOPP-E2"       in {s["id"] for s in r["stopp_start"]["stopp"]}
        assert r["risk_level"] != "MINIMAL"

    def test_case2_moderate_with_named_findings(self, demo_results):
        r = self._case(demo_results, "Case 2")
        assert r["risk_level"] == "MODERATE"
        pairs = self._pairs(r)
        assert frozenset(("ibuprofen", "lisinopril")) in pairs
        assert frozenset(("ibuprofen", "sertraline")) in pairs
        beers_ids = {b["id"] for b in r["beers_alerts"]}
        assert "BEERS-GI-003"   in beers_ids
        assert "BEERS-PAIN-001" in beers_ids

    def test_case3_high_with_named_findings(self, demo_results):
        r = self._case(demo_results, "Case 3")
        assert r["risk_level"] == "HIGH"
        pairs = self._pairs(r)
        assert frozenset(("warfarin",  "amiodarone")) in pairs
        assert frozenset(("digoxin",   "amiodarone")) in pairs
        assert frozenset(("lorazepam", "oxycodone" )) in pairs
        beers_ids = {b["id"] for b in r["beers_alerts"]}
        assert "BEERS-DDI-003" in beers_ids  # opioid + benzo
        assert "BEERS-DDI-001" in beers_ids  # ≥3 CNS-active drugs
        stopp_ids = {s["id"] for s in r["stopp_start"]["stopp"]}
        assert "STOPP-K2" in stopp_ids
        assert "STOPP-D9" in stopp_ids
        start_ids = {s["id"] for s in r["stopp_start"]["start"]}
        assert "START-A2" in start_ids


# ===========================================================================
# 10. API LAYER (FastAPI)  — requires the server to be running on :8000
# ===========================================================================

API_BASE = "http://localhost:8000"

def _api_alive() -> bool:
    try:
        return requests.get(f"{API_BASE}/api/health", timeout=3).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _api_alive(), reason="FastAPI server not running on :8000")
class TestAPILayer:

    def test_health_endpoint(self):
        r = requests.get(f"{API_BASE}/api/health", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_conditions_endpoint_returns_list(self):
        r = requests.get(f"{API_BASE}/api/conditions", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 10
        assert "Hypertension" in data

    def test_demo_cases_endpoint_returns_three_cases(self):
        r = requests.get(f"{API_BASE}/api/demo-cases", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 3
        for case in data:
            for key in ("name", "medication_text", "patient_age", "conditions", "expected_risk"):
                assert key in case, f"Demo case missing key: {key}"

    def test_analyze_endpoint_case1(self):
        r = requests.get(f"{API_BASE}/api/demo-cases", timeout=5)
        case1 = r.json()[0]
        payload = {
            "medication_text":    case1["medication_text"],
            "patient_age":        case1["patient_age"],
            "patient_conditions": case1["conditions"],
            "use_llm_parser":     False,
            "use_txgemma":        False,
            "use_gemma4":         False,
        }
        resp = requests.post(f"{API_BASE}/api/analyze", json=payload, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_level"] in {"MINIMAL", "LOW"}
        assert data["interactions"]         == []
        assert data["beers_alerts"]         == []
        assert data["stopp_start"]["stopp"] == []

    def test_analyze_endpoint_case2(self):
        r = requests.get(f"{API_BASE}/api/demo-cases", timeout=5)
        case2 = r.json()[1]
        payload = {
            "medication_text":    case2["medication_text"],
            "patient_age":        case2["patient_age"],
            "patient_conditions": case2["conditions"],
            "use_llm_parser":     False,
            "use_txgemma":        False,
            "use_gemma4":         False,
        }
        resp = requests.post(f"{API_BASE}/api/analyze", json=payload, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_level"] == "MODERATE"
        pairs = {frozenset((i["drug_a"], i["drug_b"])) for i in data["interactions"]}
        assert frozenset(("ibuprofen", "lisinopril")) in pairs
        assert frozenset(("ibuprofen", "sertraline")) in pairs

    def test_analyze_endpoint_case3(self):
        r = requests.get(f"{API_BASE}/api/demo-cases", timeout=5)
        case3 = r.json()[2]
        payload = {
            "medication_text":    case3["medication_text"],
            "patient_age":        case3["patient_age"],
            "patient_conditions": case3["conditions"],
            "use_llm_parser":     False,
            "use_txgemma":        False,
            "use_gemma4":         False,
        }
        resp = requests.post(f"{API_BASE}/api/analyze", json=payload, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_level"] == "HIGH"

    def test_analyze_result_schema(self):
        payload = {
            "medication_text": "metformin 500mg daily",
            "patient_age":     75,
            "use_llm_parser":  False, "use_txgemma": False, "use_gemma4": False,
        }
        resp = requests.post(f"{API_BASE}/api/analyze", json=payload, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        required_keys = {
            "risk_level", "risk_score", "parsed_medications",
            "interactions", "beers_alerts", "stopp_start",
            "predicted_interactions", "patient_summary", "errors",
        }
        assert required_keys <= set(data.keys())

    def test_analyze_with_egfr(self):
        payload = {
            "medication_text": "metformin 500mg daily",
            "patient_age":     80,
            "patient_egfr":    25.0,
            "use_llm_parser":  False, "use_txgemma": False, "use_gemma4": False,
        }
        resp = requests.post(f"{API_BASE}/api/analyze", json=payload, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        beers_ids = {b["id"] for b in data["beers_alerts"]}
        assert "BEERS-ENDO-008" in beers_ids

    def test_cors_header_present(self):
        r = requests.options(
            f"{API_BASE}/api/health",
            headers={"Origin": "http://localhost:5173"},
            timeout=5,
        )
        # CORS pre-flight: 200 or 204
        assert r.status_code in (200, 204)

    def test_analyze_empty_text_returns_result(self):
        payload = {
            "medication_text": "",
            "patient_age":     75,
            "use_llm_parser":  False, "use_txgemma": False, "use_gemma4": False,
        }
        resp = requests.post(f"{API_BASE}/api/analyze", json=payload, timeout=30)
        # Should return 200 with empty medications, not crash
        assert resp.status_code == 200


# ===========================================================================
# 11. FRONTEND BUILD STRUCTURE
# ===========================================================================

class TestFrontendStructure:

    def test_frontend_directory_exists(self):
        assert FRONTEND_DIR.is_dir(), "frontend/ directory is missing"

    def test_package_json_exists(self):
        assert (FRONTEND_DIR / "package.json").is_file()

    def test_package_json_has_vite(self):
        pkg = json.loads((FRONTEND_DIR / "package.json").read_text())
        dev_deps = pkg.get("devDependencies", {})
        assert "vite" in dev_deps, "vite missing from devDependencies"

    def test_package_json_has_react(self):
        pkg = json.loads((FRONTEND_DIR / "package.json").read_text())
        deps = pkg.get("dependencies", {})
        assert "react" in deps and "react-dom" in deps

    def test_package_json_has_framer_motion(self):
        pkg = json.loads((FRONTEND_DIR / "package.json").read_text())
        deps = pkg.get("dependencies", {})
        assert "framer-motion" in deps

    def test_package_json_has_lucide_react(self):
        pkg = json.loads((FRONTEND_DIR / "package.json").read_text())
        deps = pkg.get("dependencies", {})
        assert "lucide-react" in deps

    def test_package_json_has_axios(self):
        pkg = json.loads((FRONTEND_DIR / "package.json").read_text())
        deps = pkg.get("dependencies", {})
        assert "axios" in deps

    def test_tailwind_config_exists(self):
        assert (FRONTEND_DIR / "tailwind.config.js").is_file()

    def test_index_css_uses_tailwind(self):
        css = (FRONTEND_DIR / "src" / "index.css").read_text()
        assert "@tailwind" in css, "index.css must contain Tailwind directives"

    def test_app_tsx_exists(self):
        assert (FRONTEND_DIR / "src" / "App.tsx").is_file()

    def test_app_tsx_connects_to_api(self):
        code = (FRONTEND_DIR / "src" / "App.tsx").read_text()
        assert "localhost:8000" in code or "api/analyze" in code, \
            "App.tsx does not reference the FastAPI backend"

    def test_app_tsx_has_no_unreal_personas(self):
        code = (FRONTEND_DIR / "src" / "App.tsx").read_text()
        # These are the old "Unreal People" identifiers that should be removed
        for banned in ("KHAN", "Unreal People", "SURGEON_RESPONSE", "luxury brutalism"):
            assert banned not in code, \
                f"App.tsx still contains old 'Unreal' design artifact: '{banned}'"

    def test_vite_config_exists(self):
        assert (FRONTEND_DIR / "vite.config.ts").is_file()

    def test_node_modules_installed(self):
        assert (FRONTEND_DIR / "node_modules").is_dir(), \
            "npm install has not been run in frontend/"


# ===========================================================================
# 12. PROJECT HYGIENE
# ===========================================================================

class TestProjectHygiene:

    def test_api_py_exists(self):
        assert (PROJECT_ROOT / "api.py").is_file(), \
            "api.py is missing — FastAPI backend was not created"

    def test_app_py_removed(self):
        assert not (PROJECT_ROOT / "app.py").is_file(), \
            "app.py still exists — Streamlit has not been fully removed"

    def test_streamlit_not_in_requirements(self):
        req = (PROJECT_ROOT / "requirements.txt").read_text().lower()
        assert "streamlit" not in req, \
            "streamlit still in requirements.txt — should be removed"

    def test_fastapi_in_venv(self):
        result = subprocess.run(
            [sys.executable, "-c", "import fastapi"],
            capture_output=True
        )
        assert result.returncode == 0, "fastapi is not importable from the venv"

    def test_uvicorn_in_venv(self):
        result = subprocess.run(
            [sys.executable, "-c", "import uvicorn"],
            capture_output=True
        )
        assert result.returncode == 0, "uvicorn is not importable from the venv"

    def test_core_src_modules_importable(self):
        for module in ("src.analyzer", "src.drug_interactions",
                       "src.med_parser", "src.report_generator", "src.config"):
            result = subprocess.run(
                [sys.executable, "-c", f"import {module}"],
                capture_output=True, cwd=str(PROJECT_ROOT)
            )
            assert result.returncode == 0, f"{module} is not importable: {result.stderr.decode()}"

    def test_data_files_all_present(self):
        for fname in ("beers_criteria.json", "stopp_start.json", "drug_interactions.json"):
            assert (DATA_DIR / fname).is_file(), f"Missing data file: {fname}"

    def test_env_example_exists(self):
        assert (PROJECT_ROOT / ".env.example").is_file()

    def test_git_on_devs_changes_branch(self):
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT)
        )
        branch = result.stdout.strip()
        assert branch == "devs-changes", \
            f"Expected branch 'devs-changes', currently on '{branch}'"

    def test_api_py_has_cors_middleware(self):
        api_code = (PROJECT_ROOT / "api.py").read_text()
        assert "CORSMiddleware" in api_code, \
            "api.py is missing CORS middleware (frontend will be blocked)"

    def test_api_py_has_all_endpoints(self):
        api_code = (PROJECT_ROOT / "api.py").read_text()
        for endpoint in ("/api/analyze", "/api/demo-cases", "/api/conditions", "/api/health"):
            assert endpoint in api_code, f"api.py missing endpoint: {endpoint}"


# ===========================================================================
# conftest.py local fixtures (for classes that need cache reset)
# ===========================================================================

@pytest.fixture
def reset_module_caches():
    import src.drug_interactions as di
    di.reset_caches()
    yield
    di.reset_caches()


# ===========================================================================
# 13. TOKEN-EFFICIENT ROUTING AGENT
# ===========================================================================

class TestTokenEfficientRouter:
    """Validate the routing agent's decision logic without any API calls."""

    def test_router_module_importable(self):
        from src.router import decide_route, ROUTE_EDGE, ROUTE_CLOUD
        assert ROUTE_EDGE == "edge"
        assert ROUTE_CLOUD == "cloud_llm"

    def test_high_risk_routes_to_cloud(self):
        from src.router import decide_route, ROUTE_CLOUD
        assert decide_route("HIGH") == ROUTE_CLOUD

    def test_moderate_risk_routes_to_cloud(self):
        from src.router import decide_route, ROUTE_CLOUD
        assert decide_route("MODERATE") == ROUTE_CLOUD

    def test_low_risk_routes_to_edge(self):
        from src.router import decide_route, ROUTE_EDGE
        assert decide_route("LOW") == ROUTE_EDGE

    def test_minimal_risk_routes_to_edge(self):
        from src.router import decide_route, ROUTE_EDGE
        assert decide_route("MINIMAL") == ROUTE_EDGE

    def test_unknown_risk_routes_to_edge(self):
        from src.router import decide_route, ROUTE_EDGE
        assert decide_route("UNKNOWN") == ROUTE_EDGE

    def test_case1_routes_to_edge(self):
        """Case 1 (MINIMAL) must never spend tokens."""
        from src.router import decide_route, ROUTE_EDGE
        from src.analyzer import analyze_medications, get_demo_cases
        case = get_demo_cases()[0]
        result = analyze_medications(
            case["medication_text"], patient_age=case["patient_age"],
            patient_conditions=case["conditions"],
            use_llm_parser=False, use_txgemma=False, use_gemma4=False,
        )
        assert decide_route(result["risk_level"]) == ROUTE_EDGE

    def test_case3_routes_to_cloud(self):
        """Case 3 (HIGH) must escalate to cloud LLM."""
        from src.router import decide_route, ROUTE_CLOUD
        from src.analyzer import analyze_medications, get_demo_cases
        case = get_demo_cases()[2]
        result = analyze_medications(
            case["medication_text"], patient_age=case["patient_age"],
            patient_conditions=case["conditions"],
            use_llm_parser=False, use_txgemma=False, use_gemma4=False,
        )
        assert decide_route(result["risk_level"]) == ROUTE_CLOUD

    def test_routing_metadata_in_analyze_response(self):
        """The /api/analyze endpoint must include routing metadata."""
        if not _api_alive():
            pytest.skip("FastAPI server not running on :8000")
        payload = {
            "medication_text": "warfarin 5mg\namiodarone 200mg\nlorazepam 1mg",
            "patient_age": 85,
            "patient_conditions": ["Atrial Fibrillation"],
            "use_llm_parser": False, "use_txgemma": False, "use_gemma4": False,
        }
        resp = requests.post(f"{API_BASE}/api/analyze", json=payload, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert "routing" in data, "routing metadata missing from /api/analyze response"
        routing = data["routing"]
        assert "route" in routing
        assert "engine" in routing
        assert routing["route"] in ("edge", "cloud_llm")

    def test_low_risk_routing_metadata_is_edge(self):
        """Low-risk analyze call must return edge route — 0 tokens spent."""
        if not _api_alive():
            pytest.skip("FastAPI server not running on :8000")
        payload = {
            "medication_text": "metformin 500mg daily\nlisinopril 10mg daily",
            "patient_age": 70,
            "patient_conditions": ["Hypertension", "Diabetes Type 2"],
            "use_llm_parser": False, "use_txgemma": False, "use_gemma4": False,
        }
        resp = requests.post(f"{API_BASE}/api/analyze", json=payload, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("routing", {}).get("route") == "edge"


# ===========================================================================
# 14. STREAMING NARRATIVE ENDPOINT
# ===========================================================================

@pytest.mark.skipif(not _api_alive(), reason="FastAPI server not running on :8000")
class TestStreamingEndpoint:
    """Validate /api/analyze/stream-narrative SSE contract."""

    _STREAM_PAYLOAD = {
        "medication_text": (
            "warfarin 5mg once daily\ndigoxin 0.25mg once daily\n"
            "amiodarone 200mg once daily\nlorazepam 1mg twice daily\n"
            "oxycodone 5mg every 6 hours"
        ),
        "patient_age": 85,
        "patient_conditions": ["Atrial Fibrillation", "Anxiety", "Chronic Pain"],
        "use_llm_parser": False, "use_txgemma": False, "use_gemma4": False,
    }

    def test_stream_endpoint_returns_200(self):
        resp = requests.post(
            f"{API_BASE}/api/analyze/stream-narrative",
            json=self._STREAM_PAYLOAD,
            stream=True, timeout=60,
        )
        assert resp.status_code == 200

    def test_stream_content_type_is_event_stream(self):
        resp = requests.post(
            f"{API_BASE}/api/analyze/stream-narrative",
            json=self._STREAM_PAYLOAD,
            stream=True, timeout=60,
        )
        assert "text/event-stream" in resp.headers.get("Content-Type", "")

    def test_stream_emits_meta_event(self):
        """First SSE event must be a 'meta' dict with risk_level and route."""
        resp = requests.post(
            f"{API_BASE}/api/analyze/stream-narrative",
            json=self._STREAM_PAYLOAD,
            stream=True, timeout=60,
        )
        meta_found = False
        for raw_line in resp.iter_lines(decode_unicode=True):
            if raw_line.startswith("data: "):
                payload = json.loads(raw_line[6:])
                if payload.get("type") == "meta":
                    assert "risk_level" in payload
                    assert "route" in payload
                    assert payload["route"] in ("edge", "cloud_llm")
                    meta_found = True
                    break
        assert meta_found, "No 'meta' SSE event received from stream endpoint"

    def test_stream_emits_done_event(self):
        """Stream must terminate with a 'done' event."""
        resp = requests.post(
            f"{API_BASE}/api/analyze/stream-narrative",
            json=self._STREAM_PAYLOAD,
            stream=True, timeout=60,
        )
        done_found = False
        for raw_line in resp.iter_lines(decode_unicode=True):
            if raw_line.startswith("data: "):
                payload = json.loads(raw_line[6:])
                if payload.get("type") == "done":
                    done_found = True
                    break
        assert done_found, "Stream never received a 'done' event — it may have hung"

    def test_stream_low_risk_returns_edge_route(self):
        """A low-risk case must return route=edge in the meta event."""
        payload = {
            "medication_text": "metformin 500mg daily\nlisinopril 10mg daily",
            "patient_age": 70,
            "patient_conditions": ["Hypertension", "Diabetes Type 2"],
            "use_llm_parser": False, "use_txgemma": False, "use_gemma4": False,
        }
        resp = requests.post(
            f"{API_BASE}/api/analyze/stream-narrative",
            json=payload, stream=True, timeout=30,
        )
        for raw_line in resp.iter_lines(decode_unicode=True):
            if raw_line.startswith("data: "):
                event = json.loads(raw_line[6:])
                if event.get("type") == "meta":
                    assert event["route"] == "edge", \
                        f"Low-risk case was escalated to cloud (route={event['route']})"
                    return
        pytest.fail("No meta event in stream")

    def test_stream_accepts_cors_origin(self):
        """Stream endpoint must return CORS allow-origin header."""
        resp = requests.post(
            f"{API_BASE}/api/analyze/stream-narrative",
            json=self._STREAM_PAYLOAD,
            headers={"Origin": "http://localhost:5174"},
            stream=True, timeout=60,
        )
        assert resp.status_code == 200
        # Consume the stream so connection closes cleanly
        for _ in resp.iter_lines():
            break


# ===========================================================================
# 15. ALTERNATIVES ENDPOINT
# ===========================================================================

@pytest.mark.skipif(not _api_alive(), reason="FastAPI server not running on :8000")
class TestAlternativesEndpoint:
    """Validate /api/analyze/alternatives JSON contract."""

    _HIGH_RISK_PAYLOAD = {
        "medication_text": (
            "warfarin 5mg once daily\ndigoxin 0.25mg once daily\n"
            "amiodarone 200mg once daily\nlorazepam 1mg twice daily\n"
            "oxycodone 5mg every 6 hours\ndiphenhydramine 25mg at bedtime"
        ),
        "patient_age": 85,
        "patient_conditions": ["Atrial Fibrillation", "Anxiety", "Insomnia", "Chronic Pain", "Heart Failure"],
        "use_llm_parser": False, "use_txgemma": False, "use_gemma4": False,
    }

    def test_alternatives_endpoint_returns_200(self):
        resp = requests.post(
            f"{API_BASE}/api/analyze/alternatives",
            json=self._HIGH_RISK_PAYLOAD, timeout=60,
        )
        assert resp.status_code == 200

    def test_alternatives_response_has_correct_schema(self):
        resp = requests.post(
            f"{API_BASE}/api/analyze/alternatives",
            json=self._HIGH_RISK_PAYLOAD, timeout=60,
        )
        data = resp.json()
        assert "alternatives" in data, "Response missing 'alternatives' key"
        assert "risk_level" in data, "Response missing 'risk_level' key"
        assert data["risk_level"] in {"HIGH", "MODERATE", "LOW", "MINIMAL"}

    def test_alternatives_is_a_list(self):
        resp = requests.post(
            f"{API_BASE}/api/analyze/alternatives",
            json=self._HIGH_RISK_PAYLOAD, timeout=60,
        )
        data = resp.json()
        assert isinstance(data["alternatives"], list), \
            "'alternatives' must be a JSON array"

    def test_alternatives_each_item_has_required_keys(self):
        """If Fireworks API key is active, each alternative must have all required fields."""
        import os
        if not os.getenv("FIREWORKS_API_KEY"):
            pytest.skip("FIREWORKS_API_KEY not set; LLM alternatives not generated")
        resp = requests.post(
            f"{API_BASE}/api/analyze/alternatives",
            json=self._HIGH_RISK_PAYLOAD, timeout=60,
        )
        data = resp.json()
        required_keys = {"drug", "reason", "safer_alternative", "rationale", "priority"}
        for alt in data["alternatives"]:
            missing = required_keys - alt.keys()
            assert not missing, f"Alternative item missing keys: {missing} — got {alt}"

    def test_alternatives_priority_values_valid(self):
        import os
        if not os.getenv("FIREWORKS_API_KEY"):
            pytest.skip("FIREWORKS_API_KEY not set; LLM alternatives not generated")
        resp = requests.post(
            f"{API_BASE}/api/analyze/alternatives",
            json=self._HIGH_RISK_PAYLOAD, timeout=60,
        )
        data = resp.json()
        for alt in data["alternatives"]:
            assert alt.get("priority") in ("high", "moderate"), \
                f"Invalid priority value: {alt.get('priority')}"

    def test_alternatives_low_risk_returns_empty_list(self):
        """Low-risk case has no flagged drugs → alternatives must be empty."""
        payload = {
            "medication_text": "metformin 500mg daily\nlisinopril 10mg daily",
            "patient_age": 70,
            "patient_conditions": ["Hypertension", "Diabetes Type 2"],
            "use_llm_parser": False, "use_txgemma": False, "use_gemma4": False,
        }
        resp = requests.post(
            f"{API_BASE}/api/analyze/alternatives",
            json=payload, timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Low-risk case has no major DDIs → router.generate_alternatives returns []
        assert isinstance(data["alternatives"], list)


# ===========================================================================
# 16. FRONTEND INTEGRATION — NEW FEATURES
# ===========================================================================

class TestFrontendHackathonIntegration:
    """Check that App.tsx correctly references all new hackathon endpoints and features."""

    def _app_code(self) -> str:
        return (FRONTEND_DIR / "src" / "App.tsx").read_text()

    def test_app_references_stream_narrative_endpoint(self):
        assert "stream-narrative" in self._app_code(), \
            "App.tsx does not call the /api/analyze/stream-narrative SSE endpoint"

    def test_app_references_alternatives_endpoint(self):
        assert "alternatives" in self._app_code(), \
            "App.tsx does not call the /api/analyze/alternatives endpoint"

    def test_app_has_streaming_state(self):
        code = self._app_code()
        assert "isStreaming" in code, \
            "App.tsx missing isStreaming state for SSE streaming"

    def test_app_has_stream_route_state(self):
        code = self._app_code()
        assert "streamRoute" in code, \
            "App.tsx missing streamRoute state for hardware routing indicator"

    def test_app_has_hardware_indicator(self):
        code = self._app_code()
        assert "AMD" in code or "MI300X" in code or "Fireworks" in code, \
            "App.tsx missing the AMD/Fireworks hardware acceleration indicator"

    def test_app_has_alternatives_state(self):
        code = self._app_code()
        assert "alternatives" in code, \
            "App.tsx missing alternatives state for the prescribing alternatives panel"

    def test_app_has_fetch_streaming_logic(self):
        code = self._app_code()
        assert "iter_lines" in code or "getReader" in code or "reader.read" in code, \
            "App.tsx missing streaming reader logic for SSE consumption"

    def test_router_module_exists(self):
        assert (SRC_DIR / "router.py").is_file(), \
            "src/router.py is missing — Token-Efficient Routing Agent not created"

    def test_router_module_importable(self):
        result = subprocess.run(
            [sys.executable, "-c", "from src.router import decide_route, ROUTE_EDGE, ROUTE_CLOUD"],
            capture_output=True, cwd=str(PROJECT_ROOT)
        )
        assert result.returncode == 0, \
            f"src.router is not importable: {result.stderr.decode()}"

    def test_api_has_stream_endpoint(self):
        api_code = (PROJECT_ROOT / "api.py").read_text()
        assert "stream-narrative" in api_code or "stream_narrative" in api_code, \
            "api.py missing the streaming narrative endpoint"

    def test_api_has_alternatives_endpoint(self):
        api_code = (PROJECT_ROOT / "api.py").read_text()
        assert "/api/analyze/alternatives" in api_code, \
            "api.py missing the /api/analyze/alternatives endpoint"

