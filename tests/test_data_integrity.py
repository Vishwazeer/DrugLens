"""Structural integrity of the three clinical rule files."""

from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

BEERS_SEVERITIES = {"high", "moderate", "low"}
DDI_SEVERITIES = {"major", "moderate", "minor"}


def test_files_are_utf8_clean() -> None:
    for name in ("beers_criteria.json", "stopp_start.json", "drug_interactions.json"):
        text = (DATA_DIR / name).read_text(encoding="utf-8")
        assert "Â" not in text and "â€" not in text, f"mojibake in {name}"


def test_beers_entries_well_formed(beers_data: list[dict]) -> None:
    ids = [c["id"] for c in beers_data]
    assert len(ids) == len(set(ids)), "duplicate Beers ids"
    for c in beers_data:
        assert c["severity"] in BEERS_SEVERITIES, f"{c['id']}: bad severity {c['severity']}"
        for key in ("id", "category", "drug_class", "drugs", "recommendation", "rationale"):
            assert key in c, f"{c['id']}: missing {key}"
        assert isinstance(c["drugs"], list) and all(isinstance(d, str) for d in c["drugs"])


def test_beers_combination_upgrades(beers_data: list[dict]) -> None:
    by_id = {c["id"]: c for c in beers_data}
    for rule_id in ("BEERS-DDI-002", "BEERS-DDI-003", "BEERS-DDI-004", "BEERS-DDI-005",
                    "BEERS-DDI-006", "BEERS-DDI-007", "BEERS-DDI-008", "BEERS-DDI-010"):
        groups = by_id[rule_id].get("combination_groups")
        assert groups and len(groups) >= 2, f"{rule_id}: missing combination_groups"
        for group in groups:
            assert isinstance(group, list) and group
            assert all(isinstance(d, str) and d == d.lower() for d in group)

    ddi_001 = by_id["BEERS-DDI-001"]
    assert ddi_001["min_matches"] == 3
    # class placeholders replaced with real CNS-active drug names
    assert {"lorazepam", "oxycodone", "diphenhydramine"} <= set(ddi_001["drugs"])
    assert "opioids" not in ddi_001["drugs"]
    assert by_id["BEERS-DDI-009"]["min_matches"] == 2
    assert by_id["BEERS-ENDO-008"]["egfr_below"] == 45


def test_stopp_start_well_formed(stopp_start_data: dict) -> None:
    stopp = stopp_start_data["stopp"]
    start = stopp_start_data["start"]
    ids = [r["id"] for r in stopp + start]
    assert len(ids) == len(set(ids)), "duplicate STOPP/START ids"
    assert "STOPP-Q1" not in ids, "dead rule STOPP-Q1 should be removed"
    for r in stopp:
        for key in ("id", "section", "category", "criteria", "drugs", "rationale", "severity"):
            assert key in r, f"{r['id']}: missing {key}"
        assert r["drugs"] or r.get("combination_groups"), f"{r['id']}: no drug matcher"
    for r in start:
        # conditions may be empty (universal rules like annual flu vaccine)
        assert "conditions" in r, f"{r['id']}: missing conditions key"
        assert r["drugs"], f"{r['id']}: START rule without drugs to recommend"


def test_stopp_gating_upgrades(stopp_start_data: dict) -> None:
    by_id = {r["id"]: r for r in stopp_start_data["stopp"]}
    for rule_id in ("STOPP-A6", "STOPP-A8", "STOPP-A9", "STOPP-C3", "STOPP-C5",
                    "STOPP-G2", "STOPP-K2"):
        assert len(by_id[rule_id].get("combination_groups", [])) >= 2, rule_id
    assert by_id["STOPP-K1"]["min_matches"] == 2
    assert by_id["STOPP-L1"]["min_matches"] == 2
    assert by_id["STOPP-D9"]["absent_drugs"], "D9 needs laxative absence gate"
    assert by_id["STOPP-G1"]["absent_drugs"], "G1 needs PPI absence gate"
    assert by_id["STOPP-E1"]["egfr_below"] == 50
    assert by_id["STOPP-E2"]["egfr_below"] == 30
    assert by_id["STOPP-A1"]["egfr_below"] == 50


def test_ddi_entries_well_formed(ddi_data: list[dict]) -> None:
    pairs: set[tuple[str, str]] = set()
    for entry in ddi_data:
        a, b = entry["drug_a"].lower(), entry["drug_b"].lower()
        assert a == entry["drug_a"] and b == entry["drug_b"], "drug names must be lowercase"
        pair = tuple(sorted((a, b)))
        assert pair not in pairs, f"duplicate DDI pair {pair}"
        pairs.add(pair)
        assert entry["severity"] in DDI_SEVERITIES, f"{pair}: bad severity"
    assert ("ibuprofen", "sertraline") in pairs, "SSRI+NSAID entry missing"
