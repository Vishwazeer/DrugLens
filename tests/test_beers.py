"""Beers Criteria engine: age gate, combination groups, min_matches, eGFR."""

from src.drug_interactions import check_beers_criteria

CANONICAL_KEYS = {
    "id", "category", "drug_class", "matched_drugs", "recommendation",
    "rationale", "severity", "exceptions", "quality_of_evidence",
}


def _ids(results: list[dict]) -> set[str]:
    return {r["id"] for r in results}


def test_under_65_returns_no_alerts() -> None:
    assert check_beers_criteria(["diphenhydramine"], patient_age=50) == []


def test_single_drug_pim_fires_with_canonical_schema() -> None:
    results = check_beers_criteria(["diphenhydramine"], patient_age=80)
    assert "BEERS-ACH-001" in _ids(results)
    alert = next(r for r in results if r["id"] == "BEERS-ACH-001")
    assert set(alert.keys()) == CANONICAL_KEYS
    assert alert["matched_drugs"] == ["diphenhydramine"]
    assert alert["drug_class"] == "First-generation antihistamines"
    assert alert["severity"] == "high"
    assert alert["exceptions"]  # passed through from data


def test_combination_rules_do_not_fire_on_single_component() -> None:
    # The pre-fix engine spuriously fired DDI-005/007/008 on lisinopril alone
    results = check_beers_criteria(["lisinopril"], patient_age=80)
    assert _ids(results) & {"BEERS-DDI-005", "BEERS-DDI-007", "BEERS-DDI-008"} == set()

    results = check_beers_criteria(["ibuprofen"], patient_age=80)
    assert _ids(results) & {"BEERS-DDI-002", "BEERS-DDI-006", "BEERS-DDI-010"} == set()


def test_triple_whammy_requires_all_three_groups() -> None:
    two = check_beers_criteria(["lisinopril", "ibuprofen"], patient_age=80)
    assert "BEERS-DDI-005" not in _ids(two)

    three = check_beers_criteria(["lisinopril", "furosemide", "ibuprofen"], patient_age=80)
    assert "BEERS-DDI-005" in _ids(three)
    alert = next(r for r in three if r["id"] == "BEERS-DDI-005")
    assert set(alert["matched_drugs"]) == {"lisinopril", "furosemide", "ibuprofen"}


def test_opioid_benzo_combination_fires_only_together() -> None:
    assert "BEERS-DDI-003" not in _ids(check_beers_criteria(["oxycodone"], patient_age=80))
    assert "BEERS-DDI-003" in _ids(
        check_beers_criteria(["oxycodone", "lorazepam"], patient_age=80)
    )


def test_warfarin_nsaid_combination() -> None:
    assert "BEERS-DDI-006" not in _ids(check_beers_criteria(["warfarin"], patient_age=80))
    assert "BEERS-DDI-006" in _ids(
        check_beers_criteria(["warfarin", "ibuprofen"], patient_age=80)
    )


def test_cns_polypharmacy_needs_three_active_drugs() -> None:
    two = check_beers_criteria(["lorazepam", "oxycodone"], patient_age=85)
    assert "BEERS-DDI-001" not in _ids(two)

    three = check_beers_criteria(["lorazepam", "oxycodone", "diphenhydramine"], patient_age=85)
    assert "BEERS-DDI-001" in _ids(three)
    alert = next(r for r in three if r["id"] == "BEERS-DDI-001")
    assert len(alert["matched_drugs"]) == 3
    assert alert["severity"] == "high"  # styled severity, not the old "major"


def test_metformin_renal_alert_gated_on_egfr() -> None:
    assert "BEERS-ENDO-008" not in _ids(
        check_beers_criteria(["metformin"], patient_age=75, egfr=60.0)
    )
    assert "BEERS-ENDO-008" not in _ids(
        check_beers_criteria(["metformin"], patient_age=75, egfr=None)
    )
    assert "BEERS-ENDO-008" in _ids(
        check_beers_criteria(["metformin"], patient_age=75, egfr=30.0)
    )


def test_demo_case_1_regimen_triggers_no_beers_alerts() -> None:
    """The judge-facing 'mild' case: must be clean at normal renal function."""
    results = check_beers_criteria(
        ["metformin", "lisinopril", "amlodipine"],
        patient_age=70,
        conditions=["Hypertension", "Diabetes Type 2"],
        egfr=60.0,
    )
    assert results == []
