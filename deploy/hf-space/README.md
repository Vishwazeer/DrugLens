---
title: DrugLens
emoji: 💊
colorFrom: red
colorTo: pink
sdk: docker
app_port: 8000
pinned: false
license: mit
short_description: AI-powered geriatric polypharmacy risk analyzer
---

# 💊 DrugLens — Geriatric Polypharmacy Risk Analyzer

**AMD Developer Hackathon: ACT II — Track 3**

Paste an elderly patient's medication list and DrugLens audits it against
gold-standard geriatric rulesets, then escalates complex cases to a cloud LLM
for a streaming clinical narrative.

## What it does

- **Deterministic engine (offline, <1s):** 100+ curated drug–drug interactions,
  AGS Beers Criteria (2023), and STOPP/START v3 — with true combination-rule
  logic (e.g. "opioid **+** benzodiazepine", the renal "triple whammy") and
  eGFR-aware renal gating.
- **Token-efficient routing:** LOW/MINIMAL cases are answered entirely offline
  (zero tokens spent). Only MODERATE/HIGH cases escalate to the cloud model.
- **Cloud synthesis (Fireworks AI):** streaming clinical narrative + structured
  prescribing alternatives.

## Try the demo cases

1. **Case 1 — Mild:** stays quiet (no false alarms). Then set **eGFR to 25** and
   re-run to watch the renal safety rules activate live.
2. **Case 2 — Moderate:** NSAID + ACE-inhibitor (AKI risk), SSRI + NSAID (GI bleed).
3. **Case 3 — Severe:** 6 major interactions incl. the FDA black-box
   opioid + benzodiazepine combination.

## Configuration

Set as a **Space secret** (Settings → Variables and secrets):

| Name | Required | Notes |
|---|---|---|
| `FIREWORKS_API_KEY` | yes (for AI features) | Without it the deterministic engine still works via rule-based fallbacks |
| `REPORT_MODEL` | no | Defaults to `accounts/fireworks/models/deepseek-v4-pro` |

## ⚠️ Disclaimer

For **educational and research purposes only**. Not a certified diagnostic tool
and not a substitute for professional clinical judgement.
