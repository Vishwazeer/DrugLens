"""Regex medication parser and patient-info extraction."""

from src.med_parser import extract_patient_info, parse_medications, parse_medications_regex


def test_parses_standard_prescription_lines() -> None:
    meds = parse_medications_regex(
        "metformin 500mg twice daily\n"
        "lisinopril 10mg once daily\n"
        "amlodipine 5mg once daily"
    )
    assert [m["name"] for m in meds] == ["metformin", "lisinopril", "amlodipine"]
    assert meds[0]["dose"] == "500mg"
    assert meds[0]["frequency"] == "twice daily"


def test_parses_meq_dose_and_multiword_name() -> None:
    meds = parse_medications_regex("potassium chloride 20mEq once daily")
    assert meds[0]["name"] == "potassium chloride"
    assert meds[0]["dose"] == "20mEq"


def test_parses_frequency_aliases() -> None:
    meds = parse_medications_regex(
        "oxycodone 5mg every 6 hours\n"
        "diphenhydramine 25mg at bedtime\n"
        "lorazepam 1mg bid"
    )
    by_name = {m["name"]: m for m in meds}
    assert by_name["oxycodone"]["frequency"] == "every 6 hours"
    assert by_name["diphenhydramine"]["frequency"] == "once daily (bedtime)"
    assert by_name["lorazepam"]["frequency"] == "twice daily"


def test_parses_route() -> None:
    meds = parse_medications_regex("metoprolol 25mg po twice daily")
    assert meds[0]["route"] == "oral"


def test_llm_disabled_uses_regex_and_never_throws() -> None:
    meds = parse_medications("warfarin 5mg daily", use_llm=False)
    assert meds[0]["name"] == "warfarin"
    assert parse_medications("", use_llm=False) == []


def test_extract_age_and_egfr() -> None:
    info = extract_patient_info("82 year old patient, eGFR: 45, on warfarin")
    assert info["age"] == 82
    assert info["egfr"] == 45.0


def test_extract_conditions_word_boundary() -> None:
    """'pe' must not fire inside 'type', 'pepcid', or 'percocet'."""
    info = extract_patient_info(
        "type 2 diabetes patient taking pepcid and percocet for pain"
    )
    assert "pe" not in info["conditions"]
    assert "diabetes" in info["conditions"]

    info_pe = extract_patient_info("history of PE on apixaban")
    assert "pe" in info_pe["conditions"]


def test_extract_allergies() -> None:
    info = extract_patient_info("Allergies: penicillin, sulfa\nmetformin 500mg")
    assert info["allergies"] == ["penicillin", "sulfa"]

    nkda = extract_patient_info("NKDA. metformin 500mg daily")
    assert nkda["allergies"] == ["NKDA"]
