"""Drug-name normalization and condition-synonym expansion."""

from src.drug_interactions import expand_conditions, normalize_drug_name


def test_brand_aliases_resolve() -> None:
    assert normalize_drug_name("coumadin") == "warfarin"
    assert normalize_drug_name("xarelto") == "rivaroxaban"
    assert normalize_drug_name("benadryl") == "diphenhydramine"
    assert normalize_drug_name("percocet") == "oxycodone"
    assert normalize_drug_name("paracetamol") == "acetaminophen"


def test_normalization_handles_case_and_whitespace() -> None:
    assert normalize_drug_name("  Coumadin ") == "warfarin"
    assert normalize_drug_name("LASIX") == "furosemide"


def test_unknown_names_pass_through_lowercased() -> None:
    assert normalize_drug_name("Unobtainium") == "unobtainium"


def test_expand_conditions_maps_ui_labels_to_data_vocabulary() -> None:
    expanded = expand_conditions(["Diabetes Type 2"])
    assert "diabetes type 2" in expanded
    assert "type 2 diabetes" in expanded

    expanded = expand_conditions(["CHF"])
    assert "heart failure" in expanded

    expanded = expand_conditions(["DVT/PE"])
    assert {"dvt", "pe", "pulmonary embolism"} <= expanded


def test_expand_conditions_handles_empty_input() -> None:
    assert expand_conditions(None) == set()
    assert expand_conditions([]) == set()
    assert expand_conditions(["  "]) == set()


def test_expand_conditions_keeps_unknown_terms() -> None:
    assert "rare syndrome x" in expand_conditions(["Rare Syndrome X"])
