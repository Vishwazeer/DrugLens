# DrugLens — Implementation Progress

Tracking file for the hardening & demo-win plan (23 verified defects + enhancements).
Full plan: `C:\Users\navni\.claude\plans\i-need-you-to-sunny-spark.md`

Legend: ✅ done · 🔄 in progress · ⏳ pending · ⚠️ blocked/needs input

---

## Phase 0 — Tooling, baseline, Fireworks preflight — 🔄

**Goal:** safe pytest ground, live-verify the Fireworks model id, record broken baseline.

| Item | Status |
|---|---|
| `requirements-dev.txt` (pytest, ruff) | ✅ |
| `pyproject.toml` (pytest testpaths/pythonpath, ruff, requires-python ≥3.10) | ✅ |
| `git mv test_smoke.py scripts/smoke_check.py`, `test_fireworks.py → scripts/fireworks_live_check.py` | ✅ |
| `tests/__init__.py` | ✅ |
| `.venv` + all deps installed | ✅ (`DEPS OK`) |
| `pytest -q` collects cleanly (no tests yet) | ✅ (exit 5 = no tests collected, as expected) |
| Baseline capture (pre-fix demo scores) | ✅ (see below) |
| Fireworks live preflight (model id `gemma-4-31b-it`) | ⚠️ **needs FIREWORKS_API_KEY** — no `.env` present. Once the key is added to `.env`, run: `python scripts\fireworks_live_check.py` |

**Baseline (pre-fix), captured locally 2026-07-11 via `scripts\smoke_check.py`:**
- Case 1 (expected LOW) → **HIGH, score 10** — 0 interactions but 4 spurious Beers alerts + 1 spurious STOPP (combination rules firing on lisinopril alone)
- Case 2 (expected MODERATE) → **HIGH, score 27** — 9 Beers alerts (mostly spurious combination rules)
- Case 3 (expected HIGH) → HIGH, score 60 ✔ level correct, but inflated by false-positive combination alerts
- Beers alert titles print `?` (dropped `drug_class` key) — confirms engine↔UI schema mismatch
- All 3 demo cases crash the UI multiselect (StreamlitAPIException) — UI-only, not visible in this CLI run

**Phase 0 verified complete** (except Fireworks preflight, blocked on user's API key — fallback report keeps the app functional regardless).

---

## Phase 1 — Data layer + rules engines — ⏳
Combination-rule schema (`combination_groups` / `min_matches` / `egfr_below` / `absent_drugs`), canonical alert schema, DDI dedupe + duplicate removal, eGFR gating, age gates, alias cleanup, engine test suite.

## Phase 2 — Orchestrator, report, config, demo cases — ⏳
TxGemma call fix, condition/eGFR propagation, risk calibration (HIGH ≥12 / MODERATE ≥5 / LOW ≥1), `CONDITION_OPTIONS`, corrected demo cases, `_SEVERITY_SCORE` high/low, config wiring, assertive smoke script.

## Phase 3 — UI alignment & demo polish — ⏳
Canonical keys in all tabs, patient summary display, severity styling, config-driven toggles, "AI risk score N/100" labeling, manual click-through of all 3 demo cases.

## Phase 4 — Deployment & ops — ⏳
compose profiles + optional env_file, `.dockerignore`, `setup_amd_pod.sh` hardening.

## Phase 5 — Docs, CI, final QA, push — ⏳
README accuracy, `.github/workflows/ci.yml`, ruff+pytest green, full runbook, security checklist, push, Actions confirmation.

---

## Verification evidence log

*(appended after each phase)*
