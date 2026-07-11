"""Offline smoke check: the three judge demo cases must hit their risk bands.

Runs the full pipeline with all LLMs disabled (pure rules engine) and exits
non-zero if any case lands outside its expected outcome.

Usage: python scripts/smoke_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analyzer import analyze_medications, get_demo_cases  # noqa: E402

# Case 1 may legitimately be MINIMAL or LOW; the others are exact.
ACCEPTED_LEVELS: dict[str, set[str]] = {
    "MINIMAL": {"MINIMAL", "LOW"},
    "LOW": {"MINIMAL", "LOW"},
    "MODERATE": {"MODERATE"},
    "HIGH": {"HIGH"},
}


def main() -> int:
    cases = get_demo_cases()
    print(f"Demo cases loaded: {len(cases)}")
    failures: list[str] = []

    for case in cases:
        print(f"\n{'=' * 60}")
        print(f"CASE: {case['name']}")
        print(f"Patient: {case['patient_age']}yo, {', '.join(case.get('conditions', []))}")

        result = analyze_medications(
            medication_text=case["medication_text"],
            patient_age=case["patient_age"],
            patient_conditions=case.get("conditions", []),
            patient_egfr=60.0,
            use_llm_parser=False,
            use_txgemma=False,
            use_gemma4=False,
        )

        level = result["risk_level"]
        expected = case["expected_risk"]
        stopp_start = result.get("stopp_start", {})
        print(f"Risk Level: {level} (score: {result.get('risk_score', '?')}), "
              f"expected: {expected}")
        print(f"Medications parsed: {len(result.get('parsed_medications', []))}")
        print(f"Interactions: {len(result.get('interactions', []))} | "
              f"Beers: {len(result.get('beers_alerts', []))} | "
              f"STOPP: {len(stopp_start.get('stopp', []))} | "
              f"START: {len(stopp_start.get('start', []))}")

        for ix in result.get("interactions", []):
            print(f"  interaction: {ix['drug_a']} <-> {ix['drug_b']} [{ix['severity']}]")
        for alert in result.get("beers_alerts", []):
            print(f"  beers: [{alert['id']}] {alert['drug_class']} -> {alert['recommendation']}")
        for rule in stopp_start.get("stopp", []):
            print(f"  stopp: [{rule['id']}] {', '.join(rule['matched_drugs'])}")

        if result.get("errors"):
            failures.append(f"{case['name']}: pipeline errors {result['errors']}")
        if level not in ACCEPTED_LEVELS.get(expected, {expected}):
            failures.append(
                f"{case['name']}: risk level {level} not in accepted band for {expected}"
            )

    print(f"\n{'=' * 60}")
    if failures:
        print("SMOKE CHECK FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SMOKE CHECK PASSED: all demo cases in expected risk bands, no pipeline errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
