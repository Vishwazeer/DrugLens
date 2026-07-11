"""Test Fireworks API + Gemma 4 report generation."""
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from src.analyzer import analyze_medications

# Test with severe case — should trigger Gemma 4 report
r = analyze_medications(
    medication_text="warfarin 5mg daily\namiodarone 200mg daily\nlorazepam 1mg bid\noxycodone 5mg q6h",
    patient_age=82,
    patient_conditions=["atrial fibrillation", "anxiety", "chronic pain"],
    use_llm_parser=False,
    use_txgemma=False,
    use_gemma4=True,
)

print(f"Risk: {r['risk_level']} (score: {r.get('risk_score', '?')})")
print(f"Interactions: {len(r.get('interactions', []))}")
print(f"Beers: {len(r.get('beers_alerts', []))}")

report = r.get("risk_report", {})
if isinstance(report, dict) and report:
    print(f"\n--- GEMMA 4 REPORT ---")
    print(f"Overall: {report.get('overall_risk_score', 'N/A')}")
    print(f"Score: {report.get('risk_score_numeric', 'N/A')}/100")
    print(f"Summary: {report.get('summary', 'N/A')[:200]}")
    print(f"Deprescribing: {len(report.get('deprescribing_suggestions', []))} suggestions")
    print(f"Alerts: {len(report.get('key_alerts', []))} alerts")
    print(f"Recommendations: {len(report.get('recommendations', []))} recs")
else:
    print(f"\nNo Gemma 4 report generated. Errors: {r.get('errors', [])}")
