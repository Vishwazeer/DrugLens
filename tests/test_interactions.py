"""Pairwise DDI lookup engine."""

from src.drug_interactions import check_interactions

CANONICAL_KEYS = {
    "drug_a", "drug_b", "severity", "mechanism", "effect", "management",
    "evidence_level", "source",
}


def test_known_pair_found_in_both_orders() -> None:
    for meds in (["warfarin", "amiodarone"], ["amiodarone", "warfarin"]):
        results = check_interactions(meds)
        assert len(results) == 1
        assert results[0]["severity"] == "major"
        assert {results[0]["drug_a"], results[0]["drug_b"]} == {"warfarin", "amiodarone"}


def test_previously_duplicated_pair_reported_exactly_once() -> None:
    results = check_interactions(["aspirin", "warfarin"])
    assert len(results) == 1


def test_results_sorted_major_first() -> None:
    # lisinopril+ibuprofen is major; sertraline+ibuprofen is moderate
    results = check_interactions(["sertraline", "ibuprofen", "lisinopril"])
    severities = [r["severity"] for r in results]
    assert severities == sorted(severities, key=["major", "moderate", "minor", "unknown"].index)
    assert severities[0] == "major"


def test_canonical_keys_present() -> None:
    results = check_interactions(["warfarin", "amiodarone"])
    assert set(results[0].keys()) == CANONICAL_KEYS
    assert results[0]["source"] == "database"
    assert results[0]["evidence_level"] == "established"


def test_brand_names_resolve_before_lookup() -> None:
    results = check_interactions(["Coumadin", "amiodarone"])
    assert len(results) == 1


def test_new_ssri_nsaid_pair_present() -> None:
    results = check_interactions(["sertraline", "ibuprofen"])
    assert len(results) == 1
    assert results[0]["severity"] == "moderate"


def test_unknown_pair_returns_empty() -> None:
    assert check_interactions(["acetaminophen", "levothyroxine"]) == []


def test_duplicate_medication_entries_do_not_duplicate_alerts() -> None:
    results = check_interactions(["warfarin", "warfarin", "amiodarone"])
    assert len(results) == 1
