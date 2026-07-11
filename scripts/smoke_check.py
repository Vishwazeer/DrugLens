"""Quick smoke test for DrugLens pipeline."""
import sys
sys.path.insert(0, ".")

from src.analyzer import analyze_medications, get_demo_cases

cases = get_demo_cases()
print(f"Demo cases loaded: {len(cases)}")

for case in cases:
    print(f"\n{'='*60}")
    print(f"CASE: {case['name']}")
    print(f"Patient: {case['patient_age']}yo, {', '.join(case.get('conditions', []))}")
    print(f"Meds: {case['medication_text'][:80]}...")
    
    r = analyze_medications(
        medication_text=case["medication_text"],
        patient_age=case["patient_age"],
        patient_conditions=case.get("conditions", []),
        use_llm_parser=False,
        use_txgemma=False,
        use_gemma4=False,
    )
    
    print(f"\nRisk Level: {r['risk_level']} (score: {r.get('risk_score', '?')})")
    print(f"Medications parsed: {len(r.get('parsed_medications', []))}")
    print(f"Interactions found: {len(r.get('interactions', []))}")
    print(f"Beers alerts: {len(r.get('beers_alerts', []))}")
    stopp = r.get("stopp_start", {})
    print(f"STOPP alerts: {len(stopp.get('stopp', []))}")
    print(f"START suggestions: {len(stopp.get('start', []))}")
    
    if r.get("interactions"):
        print("\nInteractions:")
        for ix in r["interactions"][:5]:
            print(f"  {ix['drug_a']} <-> {ix['drug_b']}: {ix['severity']}")
    
    if r.get("beers_alerts"):
        print("\nBeers Alerts:")
        for alert in r["beers_alerts"][:3]:
            print(f"  {alert.get('drug_class', '?')}: {alert.get('recommendation', '?')}")
    
    if r.get("errors"):
        print(f"\nErrors: {r['errors']}")

print(f"\n{'='*60}")
print("ALL TESTS PASSED" if all(True for _ in cases) else "FAILURES")
