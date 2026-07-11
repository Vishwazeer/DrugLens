"""STOPP/START engine: age gate, combinations, eGFR, absence gates, synonyms."""

from src.drug_interactions import check_stopp_start

STOPP_KEYS = {
    "id", "section", "category", "criteria", "matched_drugs", "rationale",
    "severity", "recommendation",
}
START_KEYS = {
    "id", "section", "category", "criteria", "recommended_drugs",
    "conditions_matched", "rationale", "recommendation",
}


def _stopp_ids(result: dict) -> set[str]:
    return {r["id"] for r in result["stopp"]}


def _start_ids(result: dict) -> set[str]:
    return {r["id"] for r in result["start"]}


def test_under_65_returns_nothing() -> None:
    result = check_stopp_start(["lorazepam"], patient_age=50, conditions=["Insomnia"])
    assert result == {"stopp": [], "start": []}


def test_stopp_canonical_schema() -> None:
    result = check_stopp_start(["lorazepam"], patient_age=80)
    assert "STOPP-D5" in _stopp_ids(result)  # benzodiazepine >= 4 weeks
    rule = next(r for r in result["stopp"] if r["id"] == "STOPP-D5")
    assert set(rule.keys()) == STOPP_KEYS
    assert rule["matched_drugs"] == ["lorazepam"]
    assert rule["criteria"]
    assert rule["recommendation"]  # falls back to criteria text
    assert rule["severity"] == "high"


def test_ace_inhibitor_alone_does_not_fire_a9() -> None:
    result = check_stopp_start(["lisinopril"], patient_age=80)
    assert "STOPP-A9" not in _stopp_ids(result)


def test_ace_plus_potassium_sparing_fires_a9() -> None:
    result = check_stopp_start(["lisinopril", "spironolactone"], patient_age=80)
    assert "STOPP-A9" in _stopp_ids(result)


def test_opioid_benzo_combination_k2() -> None:
    alone = check_stopp_start(["oxycodone"], patient_age=80)
    assert "STOPP-K2" not in _stopp_ids(alone)
    combo = check_stopp_start(["oxycodone", "lorazepam"], patient_age=80)
    assert "STOPP-K2" in _stopp_ids(combo)


def test_two_or_more_opioids_k1() -> None:
    one = check_stopp_start(["oxycodone"], patient_age=80)
    assert "STOPP-K1" not in _stopp_ids(one)
    two = check_stopp_start(["oxycodone", "tramadol"], patient_age=80)
    assert "STOPP-K1" in _stopp_ids(two)


def test_opioid_without_laxative_d9_absence_gate() -> None:
    without = check_stopp_start(["oxycodone"], patient_age=80)
    assert "STOPP-D9" in _stopp_ids(without)
    with_laxative = check_stopp_start(["oxycodone", "senna"], patient_age=80)
    assert "STOPP-D9" not in _stopp_ids(with_laxative)


def test_nsaid_renal_e1_gated_on_egfr() -> None:
    assert "STOPP-E1" in _stopp_ids(
        check_stopp_start(["ibuprofen"], patient_age=80, egfr=40.0)
    )
    assert "STOPP-E1" not in _stopp_ids(
        check_stopp_start(["ibuprofen"], patient_age=80, egfr=60.0)
    )
    assert "STOPP-E1" not in _stopp_ids(
        check_stopp_start(["ibuprofen"], patient_age=80, egfr=None)
    )


def test_metformin_renal_e2_gated_on_egfr() -> None:
    assert "STOPP-E2" in _stopp_ids(
        check_stopp_start(["metformin"], patient_age=80, egfr=25.0)
    )
    assert "STOPP-E2" not in _stopp_ids(
        check_stopp_start(["metformin"], patient_age=80, egfr=45.0)
    )


def test_start_suggests_ace_inhibitor_in_heart_failure() -> None:
    result = check_stopp_start(["furosemide"], patient_age=80, conditions=["Heart Failure"])
    assert "START-A2" in _start_ids(result)
    rule = next(r for r in result["start"] if r["id"] == "START-A2")
    assert set(rule.keys()) == START_KEYS
    assert "lisinopril" in rule["recommended_drugs"]
    assert rule["conditions_matched"]


def test_start_suppressed_when_already_on_recommended_drug() -> None:
    result = check_stopp_start(
        ["furosemide", "lisinopril"], patient_age=80, conditions=["Heart Failure"]
    )
    assert "START-A2" not in _start_ids(result)


def test_start_matches_ui_condition_label_via_synonyms() -> None:
    """'Diabetes Type 2' (UI label) must match data vocabulary 'diabetes type 2'."""
    result = check_stopp_start([], patient_age=75, conditions=["Diabetes Type 2"])
    assert "START-G1" in _start_ids(result)  # metformin first-line


def test_universal_start_rule_fires_without_conditions() -> None:
    """START-I1 (annual influenza vaccine) applies to every patient >= 65."""
    result = check_stopp_start(["metformin"], patient_age=70, conditions=[])
    assert "START-I1" in _start_ids(result)
    rule = next(r for r in result["start"] if r["id"] == "START-I1")
    assert rule["conditions_matched"] == []

    on_vaccine = check_stopp_start(["influenza vaccine"], patient_age=70)
    assert "START-I1" not in _start_ids(on_vaccine)
