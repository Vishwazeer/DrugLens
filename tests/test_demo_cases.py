"""End-to-end offline runs of the three judge demo cases.

These freeze the calibrated risk bands and the named must-have findings so
demo behavior cannot silently regress.
"""

import pytest

from src.analyzer import analyze_medications, get_demo_cases


@pytest.fixture(scope="module")
def demo_results() -> dict[str, dict]:
    results = {}
    for case in get_demo_cases():
        results[case["name"]] = analyze_medications(
            medication_text=case["medication_text"],
            patient_age=case["patient_age"],
            patient_conditions=case["conditions"],
            patient_egfr=60.0,
            use_llm_parser=False,
            use_txgemma=False,
            use_gemma4=False,
        )
    return results


def _case(demo_results: dict, prefix: str) -> dict:
    return next(v for k, v in demo_results.items() if k.startswith(prefix))


def _interaction_pairs(result: dict) -> set[frozenset]:
    return {frozenset((i["drug_a"], i["drug_b"])) for i in result["interactions"]}


def test_case_1_is_minimal_or_low(demo_results: dict) -> None:
    result = _case(demo_results, "Case 1")
    assert result["risk_level"] in {"MINIMAL", "LOW"}
    assert result["interactions"] == []
    assert result["beers_alerts"] == []
    assert result["stopp_start"]["stopp"] == []
    assert not result["errors"]


def test_case_1_egfr_25_activates_renal_rules() -> None:
    """The live-demo moment: dropping eGFR to 25 must surface renal alerts."""
    case = get_demo_cases()[0]
    result = analyze_medications(
        medication_text=case["medication_text"],
        patient_age=case["patient_age"],
        patient_conditions=case["conditions"],
        patient_egfr=25.0,
        use_llm_parser=False,
        use_txgemma=False,
        use_gemma4=False,
    )
    assert "BEERS-ENDO-008" in {b["id"] for b in result["beers_alerts"]}
    assert "STOPP-E2" in {r["id"] for r in result["stopp_start"]["stopp"]}
    assert result["risk_level"] != "MINIMAL"


def test_case_2_is_moderate_with_named_findings(demo_results: dict) -> None:
    result = _case(demo_results, "Case 2")
    assert result["risk_level"] == "MODERATE"
    pairs = _interaction_pairs(result)
    assert frozenset(("ibuprofen", "lisinopril")) in pairs  # AKI risk (major)
    assert frozenset(("ibuprofen", "sertraline")) in pairs  # GI bleed (moderate)
    beers_ids = {b["id"] for b in result["beers_alerts"]}
    assert "BEERS-GI-003" in beers_ids  # long-term PPI
    assert "BEERS-PAIN-001" in beers_ids  # chronic NSAID
    assert not result["errors"]


def test_case_3_is_high_with_named_findings(demo_results: dict) -> None:
    result = _case(demo_results, "Case 3")
    assert result["risk_level"] == "HIGH"
    pairs = _interaction_pairs(result)
    assert frozenset(("warfarin", "amiodarone")) in pairs
    assert frozenset(("digoxin", "amiodarone")) in pairs
    assert frozenset(("lorazepam", "oxycodone")) in pairs  # FDA black box
    beers_ids = {b["id"] for b in result["beers_alerts"]}
    assert "BEERS-DDI-003" in beers_ids  # opioid + benzo combination
    assert "BEERS-DDI-001" in beers_ids  # >=3 CNS-active drugs
    stopp_ids = {r["id"] for r in result["stopp_start"]["stopp"]}
    assert "STOPP-K2" in stopp_ids  # opioid + benzo
    assert "STOPP-D9" in stopp_ids  # opioid without laxative
    start_ids = {r["id"] for r in result["stopp_start"]["start"]}
    assert "START-A2" in start_ids  # ACE inhibitor for heart failure
    assert not result["errors"]


def test_no_demo_case_reports_errors(demo_results: dict) -> None:
    for name, result in demo_results.items():
        assert not result["errors"], f"{name}: {result['errors']}"
