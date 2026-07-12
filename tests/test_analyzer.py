"""Orchestrator: TxGemma invocation, info merging, risk weights, fallbacks."""

import pytest

import src.analyzer as analyzer
from src.analyzer import _compute_risk_level, analyze_medications


def _analyze_offline(text: str, **kwargs) -> dict:
    kwargs.setdefault("use_llm_parser", False)
    kwargs.setdefault("use_txgemma", False)
    kwargs.setdefault("use_gemma4", False)
    return analyze_medications(text, **kwargs)


def test_txgemma_called_with_drug_names_and_known_interactions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the arity bug that silently disabled TxGemma."""
    calls: list[tuple] = []

    def spy(medications: list[str], known_interactions: list[dict]) -> list[dict]:
        calls.append((medications, known_interactions))
        return [{"drug_a": "a", "drug_b": "b", "predicted_interaction": "x",
                 "confidence": "low", "severity": "unknown"}]

    monkeypatch.setattr(analyzer, "predict_unknown_interactions", spy)
    result = _analyze_offline(
        "warfarin 5mg daily\namiodarone 200mg daily", patient_age=80, use_txgemma=True
    )

    assert len(calls) == 1, "predict_unknown_interactions must be invoked exactly once"
    medications, known = calls[0]
    assert "warfarin" in medications and "amiodarone" in medications
    assert known and known[0]["severity"] == "major"  # real interactions passed through
    assert result["predicted_interactions"]
    assert not result["errors"]


def test_extracted_conditions_reach_rule_engines() -> None:
    """Conditions embedded in pasted notes must drive START suggestions."""
    result = _analyze_offline(
        "82yo with heart failure\nfurosemide 40mg daily", patient_age=82
    )
    assert "heart failure" in [c.lower() for c in result["patient_info"]["conditions"]]
    start_ids = {r["id"] for r in result["stopp_start"]["start"]}
    assert "START-A2" in start_ids  # ACE inhibitor for heart failure


def test_explicit_conditions_win_and_merge_with_extracted() -> None:
    result = _analyze_offline(
        "patient with copd\nmetformin 500mg bid",
        patient_age=75,
        patient_conditions=["Hypertension"],
    )
    lower = [c.lower() for c in result["patient_info"]["conditions"]]
    assert "hypertension" in lower and "copd" in lower


def test_extracted_egfr_used_when_argument_missing() -> None:
    result = _analyze_offline(
        "eGFR: 25\nmetformin 500mg twice daily", patient_age=80, patient_egfr=None
    )
    assert result["patient_info"]["egfr"] == 25.0
    beers_ids = {b["id"] for b in result["beers_alerts"]}
    assert "BEERS-ENDO-008" in beers_ids  # renal metformin alert from extracted eGFR


def test_explicit_egfr_argument_wins_over_text() -> None:
    result = _analyze_offline(
        "eGFR: 25\nmetformin 500mg twice daily", patient_age=80, patient_egfr=90.0
    )
    assert result["patient_info"]["egfr"] == 90.0
    assert {b["id"] for b in result["beers_alerts"]} == set()


def test_parse_failure_falls_back_and_still_analyzes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(text: str, use_llm: bool = True) -> list[dict]:
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(analyzer, "parse_medications", boom)
    result = _analyze_offline("warfarin, amiodarone", patient_age=80)
    assert any("parsing failed" in e.lower() for e in result["errors"])
    assert len(result["parsed_medications"]) == 2
    assert len(result["interactions"]) == 1  # fallback names still checked


def test_risk_weights_and_thresholds() -> None:
    def synthetic(n_major: int = 0, n_moderate: int = 0, n_beers_high: int = 0,
                  n_stopp_high: int = 0, n_predicted: int = 0) -> dict:
        return {
            "interactions": [{"severity": "major"}] * n_major
                            + [{"severity": "moderate"}] * n_moderate,
            "beers_alerts": [{"severity": "high"}] * n_beers_high,
            "stopp_start": {"stopp": [{"severity": "high"}] * n_stopp_high, "start": []},
            "predicted_interactions": [{}] * n_predicted,
        }

    empty = synthetic()
    assert _compute_risk_level(empty) == "MINIMAL" and empty["risk_score"] == 0

    low = synthetic(n_moderate=1)  # 2 points
    assert _compute_risk_level(low) == "LOW"

    moderate = synthetic(n_major=1, n_beers_high=1)  # 5 points
    assert _compute_risk_level(moderate) == "MODERATE"

    high = synthetic(n_major=3, n_beers_high=1, n_stopp_high=1)  # 13 points
    assert _compute_risk_level(high) == "HIGH"

    predicted_only = synthetic(n_predicted=2)  # 2 points
    assert _compute_risk_level(predicted_only) == "LOW"


def test_cloud_calls_gated_off_when_use_gemma4_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """use_gemma4=False must make NO cloud call (report or patient summary)."""
    calls: list[str] = []
    monkeypatch.setattr(analyzer, "generate_risk_report",
                        lambda **k: calls.append("report") or {})
    monkeypatch.setattr(analyzer, "generate_patient_summary",
                        lambda **k: calls.append("summary") or "x")

    result = _analyze_offline("warfarin 5mg daily", patient_age=80, use_gemma4=False)
    assert calls == [], "no cloud functions should run when use_gemma4 is off"
    assert result["risk_report"] == {}
    assert result["patient_summary"] == ""


def test_patient_summary_generated_when_use_gemma4_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(analyzer, "generate_risk_report",
                        lambda **k: calls.append("report") or {"overall_risk_score": "low"})
    monkeypatch.setattr(analyzer, "generate_patient_summary",
                        lambda **k: calls.append("summary") or "a plain-English summary")

    result = analyze_medications(
        "warfarin 5mg daily", patient_age=80,
        use_llm_parser=False, use_txgemma=False, use_gemma4=True,
    )
    assert calls == ["report", "summary"]
    assert result["patient_summary"] == "a plain-English summary"


def test_result_contains_all_documented_keys() -> None:
    result = _analyze_offline("metformin 500mg daily", patient_age=70)
    expected_keys = {
        "parsed_medications", "patient_info", "interactions", "beers_alerts",
        "stopp_start", "predicted_interactions", "risk_report",
        "patient_summary", "errors", "risk_level", "risk_score",
    }
    assert expected_keys <= set(result.keys())
    assert {"age", "conditions", "egfr"} <= set(result["patient_info"].keys())


def test_demo_conditions_subset_of_ui_options() -> None:
    from src.analyzer import CONDITION_OPTIONS, get_demo_cases

    for case in get_demo_cases():
        for cond in case["conditions"]:
            assert cond in CONDITION_OPTIONS, (
                f"{case['name']}: condition {cond!r} not a UI option — "
                "must be a valid option served by /api/conditions"
            )
