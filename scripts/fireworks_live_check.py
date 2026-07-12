"""Live Fireworks preflight: verify API key, model id, and cloud report.

Requires FIREWORKS_API_KEY in .env or the environment. Exits non-zero on any
failure so it can gate a demo-day checklist.

Usage: python scripts/fireworks_live_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src import config  # noqa: E402  (import after load_dotenv so env is populated)
from src.analyzer import analyze_medications  # noqa: E402


def main() -> int:
    if not config.FIREWORKS_API_KEY:
        print("FAIL: FIREWORKS_API_KEY is not set (.env missing or empty).")
        return 1

    print(f"Base URL:     {config.FIREWORKS_BASE_URL}")
    print(f"Report model: {config.REPORT_MODEL}")
    print(f"JSON mode:    {config.REPORT_JSON_MODE}")

    # --- Preflight 1: can the configured model actually complete a request? ---
    # A real mini-completion is authoritative; the /models list only shows an
    # account's deployed models and can false-negative on served models.
    import requests

    probe = requests.post(
        f"{config.FIREWORKS_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {config.FIREWORKS_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.REPORT_MODEL,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        },
        timeout=30,
    )
    if probe.status_code == 200:
        print("Model verified — completed a live request.")
    else:
        print(f"FAIL: model probe returned HTTP {probe.status_code}: {probe.text[:200]}")
        avail = requests.get(
            f"{config.FIREWORKS_BASE_URL}/models",
            headers={"Authorization": f"Bearer {config.FIREWORKS_API_KEY}"},
            timeout=15,
        )
        if avail.status_code == 200:
            ids = sorted(m.get("id", "") for m in avail.json().get("data", []))
            print(f"Models available to this account: {ids or 'none'}")
            print("Set REPORT_MODEL in .env to one of the above, then re-run.")
        return 1

    # --- Preflight 2: end-to-end report on the severe demo case ---
    result = analyze_medications(
        medication_text=(
            "warfarin 5mg daily\namiodarone 200mg daily\n"
            "lorazepam 1mg bid\noxycodone 5mg q6h"
        ),
        patient_age=82,
        patient_conditions=["Atrial Fibrillation", "Anxiety", "Chronic Pain"],
        patient_egfr=55.0,
        use_llm_parser=False,
        use_txgemma=False,
        use_gemma4=True,
    )

    print(f"\nRisk: {result['risk_level']} (score: {result.get('risk_score', '?')})")
    print(f"Interactions: {len(result.get('interactions', []))}")
    print(f"Beers: {len(result.get('beers_alerts', []))}")

    report = result.get("risk_report", {})
    summary = report.get("summary", "")
    print("\n--- CLOUD REPORT ---")
    print(f"Overall: {report.get('overall_risk_score', 'N/A')}")
    print(f"AI risk score: {report.get('risk_score_numeric', 'N/A')}/100")
    print(f"Summary: {summary[:300]}")
    print(f"Deprescribing suggestions: {len(report.get('deprescribing_suggestions', []))}")
    print(f"Key alerts: {len(report.get('key_alerts', []))}")
    print(f"Recommendations: {len(report.get('recommendations', []))}")
    print(f"\nPatient summary ({len(result.get('patient_summary', ''))} chars):")
    print(result.get("patient_summary", "")[:400])

    if result.get("errors"):
        print(f"\nFAIL: pipeline errors: {result['errors']}")
        return 1
    if not report:
        print("\nFAIL: no report generated.")
        return 1
    print("\nLIVE CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
