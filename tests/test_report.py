"""Report generator: fallback scoring, JSON parsing, LLM pass-through."""

import json

import pytest

import src.report_generator as rg
from src.report_generator import (
    _fallback_report,
    _parse_json_response,
    generate_patient_summary,
    generate_risk_report,
)


def test_severity_score_high_outranks_moderate() -> None:
    """Regression: 'high' Beers alerts used to score BELOW 'moderate' ones."""
    high = _fallback_report([], [{"severity": "high", "matched_drugs": ["a"],
                                  "recommendation": "avoid"}], {"stopp": [], "start": []})
    moderate = _fallback_report([], [{"severity": "moderate", "matched_drugs": ["a"],
                                      "recommendation": "avoid"}], {"stopp": [], "start": []})
    assert high["risk_score_numeric"] > moderate["risk_score_numeric"]


def test_fallback_report_uses_canonical_keys() -> None:
    report = _fallback_report(
        interactions=[{"drug_a": "warfarin", "drug_b": "amiodarone",
                       "severity": "major", "effect": "bleeding",
                       "management": "reduce dose"}],
        beers_alerts=[{"severity": "high", "matched_drugs": ["lorazepam"],
                       "recommendation": "Avoid"}],
        stopp_start={"stopp": [{"severity": "high", "matched_drugs": ["oxycodone"],
                                "recommendation": "review"}],
                     "start": [{"recommended_drugs": ["lisinopril"],
                                "recommendation": "ACE inhibitor in HF"}]},
    )
    assert any("lorazepam" in alert for alert in report["key_alerts"])
    assert any("oxycodone" in alert for alert in report["key_alerts"])
    assert any("lisinopril" in rec for rec in report["recommendations"])
    assert report["overall_risk_score"] in {"low", "moderate", "high"}
    assert 0 <= report["risk_score_numeric"] <= 100


def test_parse_json_response_strips_markdown_fences() -> None:
    raw = '```json\n{"overall_risk_score": "high"}\n```'
    assert _parse_json_response(raw) == {"overall_risk_score": "high"}


def test_parse_json_response_extracts_embedded_object() -> None:
    raw = 'Here is the report:\n{"overall_risk_score": "low"}\nThanks!'
    assert _parse_json_response(raw) == {"overall_risk_score": "low"}


def test_parse_json_response_returns_none_for_garbage() -> None:
    assert _parse_json_response("not json at all") is None


def test_no_api_key_returns_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.FIREWORKS_API_KEY", "")
    report = generate_risk_report([], [], [], {"stopp": [], "start": []}, [], {})
    assert report["summary"] == "No significant issues identified."


def test_live_report_parsed_from_mocked_llm(
    monkeypatch: pytest.MonkeyPatch, fake_openai: type
) -> None:
    monkeypatch.setattr("src.config.FIREWORKS_API_KEY", "test-key")
    fake_openai.canned_content = json.dumps({
        "overall_risk_score": "high",
        "risk_score_numeric": 85,
        "summary": "patient-friendly summary",
        "clinical_summary": "clinical detail",
        "deprescribing_suggestions": [{"drug": "lorazepam", "reason": "falls",
                                       "alternative": "CBT-I", "priority": "High"}],
        "key_alerts": ["opioid + benzo"],
        "recommendations": ["taper benzodiazepine"],
    })
    monkeypatch.setattr(rg, "OpenAI", fake_openai)

    report = generate_risk_report(
        [{"name": "oxycodone"}], [], [], {"stopp": [], "start": []}, [], {"age": 80}
    )
    assert report["overall_risk_score"] == "high"
    assert report["risk_score_numeric"] == 85
    assert report["deprescribing_suggestions"][0]["drug"] == "lorazepam"
    assert fake_openai.last_kwargs is not None
    assert fake_openai.last_kwargs["model"]  # routed through config


def test_llm_garbage_falls_back(monkeypatch: pytest.MonkeyPatch, fake_openai: type) -> None:
    monkeypatch.setattr("src.config.FIREWORKS_API_KEY", "test-key")
    fake_openai.canned_content = "sorry, I cannot help with that"
    monkeypatch.setattr(rg, "OpenAI", fake_openai)

    report = generate_risk_report([], [], [], {"stopp": [], "start": []}, [], {})
    assert report["summary"] == "No significant issues identified."  # fallback path


def test_patient_summary_template_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.FIREWORKS_API_KEY", "")
    summary = generate_patient_summary(
        risk_report={"overall_risk_score": "moderate", "risk_score_numeric": 40,
                     "key_alerts": ["NSAID + ACE inhibitor"],
                     "recommendations": ["use acetaminophen"]},
        medications=[{"name": "ibuprofen"}, {"name": "lisinopril"}],
    )
    assert "2 medication(s)" in summary
    assert "MODERATE" in summary
    assert "doctor" in summary.lower()
