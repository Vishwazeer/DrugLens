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

## Phase 1 — Data layer + rules engines — ✅

**What was built:**
- **Data-schema upgrade** (all 3 JSON files): optional gating keys with AND semantics — `combination_groups` (every group must have ≥1 matched drug), `min_matches` (≥N distinct matches), `egfr_below` (fires only when eGFR known and below N), `absent_drugs` (STOPP: fires only when no protective co-prescription). Upgraded: Beers DDI-002…008/010 → groups, DDI-001 → min_matches 3 + real CNS drug list (replaces class-name placeholders AND the engine's hard-coded CNS block), DDI-009 → min_matches 2, ENDO-008 → egfr_below 45; STOPP A6/A8/A9/C3/C5/G2/K2 → groups, K1/L1 → min_matches 2, D9 → laxative absence gate, G1 → PPI absence gate, E1/E2/A1 → egfr_below 50/30/50; dead STOPP-Q1 deleted.
- **DDI DB**: 4 reversed duplicate pairs removed (aspirin/warfarin, naproxen/warfarin, HCTZ/lithium, clopidogrel/omeprazole → 102 entries), sertraline+ibuprofen (SSRI+NSAID GI bleed, moderate) added.
- **Engine rewrite** (`src/drug_interactions.py`): shared `_rule_matches` + `_passes_patient_gates` helpers; canonical alert schema (Beers: id/category/drug_class/matched_drugs/recommendation/rationale/severity/exceptions/quality_of_evidence; STOPP: id/section/category/criteria/matched_drugs/rationale/severity/recommendation; START: +recommended_drugs/conditions_matched); `check_interactions` dedupes (break per pair) and passes through evidence_level/source; whole-function age<65 gates; `CONDITION_SYNONYM_GROUPS`+`expand_conditions()` bridging UI labels ↔ rule vocabulary; alias cleanup (rivarelbaan typo gone, paracetamol added); deleted dead `drug_classes` path; `reset_caches()` test hook.
- **Discovered & fixed during testing:** START-I1/I2 (universal vaccine rules with empty `conditions`) could never fire — engine now supports universal START rules.
- **Tests:** 42 passing — conftest (network-blocked, cache isolation, FakeOpenAI factory), test_data_integrity, test_normalize, test_interactions, test_beers, test_stopp_start.

**Verification evidence:** `pytest -q` → 42 passed. Engine probe of the 3 demo regimens: Case 1 → 0 interactions/0 Beers/0 STOPP (score 0, MINIMAL — was HIGH/10); Case 2 → 2 real interactions + 3 legit Beers + STOPP-F1 (score 10, MODERATE — was HIGH/27); Case 3 → 6 major interactions + 7 Beers + 6 STOPP (score 39, HIGH ✔).

## Phase 2 — Orchestrator, report, config, demo cases — ✅

**What was built:**
- **TxGemma fixed (D1):** `analyzer.py` now calls `predict_unknown_interactions(drug_names, result["interactions"])` — Model 2 of the pipeline runs for the first time; regression-tested with a spy.
- **Condition/eGFR propagation (D11):** conditions extracted from pasted notes are merged (union, explicit args win) into `patient_info` and passed to BOTH rule engines along with merged eGFR; extracted eGFR fills in when the argument is absent.
- **Risk calibration (D3/D14):** weights interactions major=3/moderate=2/minor=1, Beers/STOPP high=2 else 1, predicted=1, START=0; thresholds HIGH ≥12 / MODERATE ≥5 / LOW ≥1 / else MINIMAL. Rule-based scale drives the top card; the report's 0-100 scale stays inside the AI Report tab.
- **Demo cases (D2/D18):** conditions now use exact UI labels (shared `CONDITION_OPTIONS` constant in analyzer — the multiselect crash is structurally impossible, enforced by test); Case 1 description now advertises the eGFR-25 live renal demo; Case 2 description corrected (sertraline+ibuprofen instead of the impossible triple whammy claim); Case 1 expected_risk = MINIMAL.
- **Report generator (D12):** `_SEVERITY_SCORE` covers high(25)/low(5) — high-severity Beers alerts no longer score below moderate ones; canonical `matched_drugs`/`recommended_drugs` keys consumed; STOPP scoring severity-weighted.
- **Config wiring (D15):** `src/config.py` is the single settings source; med_parser/ddi_predictor/report_generator read endpoints & keys via `config.X` at call time; USE_* flags default false/false/true (CPU-first).
- **Parser bugs (D11 + new):** word-boundary condition keywords ("pe" no longer matches "type"/"pepcid"); **new bug found by tests:** frequency alias "od" matched inside "oxycodone" (→ wrong "once daily") — freq/route regexes now use alphanumeric look-arounds.
- **Scripts (D23):** `smoke_check.py` asserts risk bands + zero pipeline errors with a real exit code; `fireworks_live_check.py` is a full preflight (key check → live /models id verification → end-to-end report).
- **Tests:** +31 (test_analyzer, test_med_parser, test_report, test_demo_cases) → 73 total.

**Verification evidence:** `pytest -q` → 73 passed · `ruff check .` → clean · `scripts\smoke_check.py` → exit 0 (Case 1 MINIMAL score 0 / Case 2 MODERATE score 10 / Case 3 HIGH score 39, no pipeline errors).

## Phase 3 — UI alignment & demo polish — ✅

**What was built (`app.py`):**
- Beers tab shows `[id] drug_class — recommendation` titles with matched drugs, rationale, category, and exceptions (was "Unknown" + blanks).
- STOPP tab styled by rule severity (high/moderate) with real criteria text and matched drugs; START tab reads `recommended_drugs`.
- AI Report tab: "🤖 AI risk score: N/100" heading with caption distinguishing it from the rule-based overview card; Key Alerts section added; Patient-Friendly Summary now reads `results["patient_summary"]` (displays for the first time).
- Interaction cards gained an Evidence line; sidebar toggles default from `config.USE_*` (docker env flags now effective); conditions multiselect uses the shared `CONDITION_OPTIONS`; unused imports removed (ruff-clean).

**Verification evidence (live browser click-through via Playwright, headless Streamlit on :8599):**
- Case 1 loads without exception (the old StreamlitAPIException is gone), Analyze → MINIMAL / 3 meds / 0 interactions / 0 alerts; AI Report tab shows fallback score 10/100, START vaccine recommendations, patient summary.
- Case 3 → HIGH / 8 meds / 6 interactions / 13 criteria alerts; all 6 major interaction cards render with Evidence; Beers cards fully populated ([BEERS-DDI-001] shows the 3 matched CNS drugs); STOPP-K2 HIGH styling; START-A2 suggested drugs listed.
- eGFR live demo: Case 1 re-analyzed at eGFR 25 → LOW with [STOPP-E2] Renal HIGH (metformin) surfacing, matching the sidebar tip.
- Browser console: 0 errors, 0 warnings. `pytest -q` 73 passed; `ruff check .` clean.

## Phase 4 — Deployment & ops — ✅

**What was built:**
- `docker-compose.yml`: `app` service moved into the `gpu` profile (no more double-bind of 8501 under cpu-only, no dependency failure on plain `up`); both app services use `env_file: {path: .env, required: false}` (Compose ≥2.24 noted inline); gpu app sets USE_LLM_PARSER/USE_TXGEMMA=true so the pod runs the full 3-model pipeline out of the box.
- `.dockerignore` (new): `.env`, `.git`, `.venv`, caches, tests/, scripts/, `.github/` — a local `.env` can no longer be baked into images by `COPY . .`.
- `setup_amd_pod.sh`: env loading via `set -a; . <(tr -d '\r' < .env); set +a` (CRLF- and space-safe); exports `HUGGING_FACE_HUB_TOKEN` (read natively by vLLM) with optional non-deprecated `hf auth login`.

**Verification evidence:** with `.env` absent — `docker compose --profile cpu-only config` exit 0 (services: app-cpu only), `--profile gpu config` exit 0 (medgemma, txgemma, app), no-profile `config --services` lists nothing (no accidental starts); `bash -n setup_amd_pod.sh` OK.

## Phase 5 — Frontend redesign (user request) — ✅

**Decision:** kept Streamlit (a framework rewrite days before judging would invalidate the verified Docker/compose/test/run stack for zero functional gain) and replaced the entire presentation layer with a **"clinical instrument panel"** design system.

**What was built (`app.py` + new `.streamlit/config.toml`):**
- Design tokens: deep-ink layered surfaces with radial glows + SVG noise grain, hairline borders, AMD-red signature accent, severity palette (red/amber/green/blue), typography = Instrument Sans (UI) + Instrument Serif italic (tagline) + Spline Sans Mono (all data, ids, numerals, labels).
- Hero header: Drug**Lens** wordmark, serif tagline "a second pair of eyes for every prescription", animated ECG trace (CSS stroke-dashoffset), mono pipeline chips (per-model role labels).
- Stat tiles: corner-bracket instrument tiles with staggered rise animation; risk tile has pulsing severity dot + a threshold track showing the score against the MOD/HIGH cut-points.
- Alert cards: severity rail + gradient wash, mono rule-id chips, right-aligned severity tags, hover micro-interactions; shared `alert_card()` renderer for interactions/Beers/STOPP/START/deprescribing.
- Tabs restyled as a segmented control; section headers as mono small-caps rules with counts; styled empty-states; refined footer.
- Interaction matrix rebuilt per the dataviz method: **validated** sequential severity ramp (#EDCB6B→#CE6C28→#E14953 — CVD ΔE 20.5 pass, contrast pass via `validate_palette.js`), 3px cell gaps, discrete 4-band legend, mono tick labels, per-cell hover tooltips, recessive axes.
- `.streamlit/config.toml` theme (primaryColor = brand red) so native widgets — toggles, multiselect chips, focus rings — match automatically.
- Streamlit chrome hidden (menu/footer), `prefers-reduced-motion` respected.

**Verification evidence:** logic untouched — `pytest -q` 73 passed, `ruff check .` clean after rewrite; server restarted with theme; full-page screenshots reviewed at 1440×960 (landing, Case 3 overview, interaction cards, matrix, Beers tab) — all canonical fields render, layout clean, 0 console errors/warnings.

## Phase 6 — Docs, CI, final QA, push — ✅

**What was built:**
- **README accuracy pass:** Python ≥3.10 requirement; new Testing & Quality Gates section (ruff/pytest/smoke/live-preflight commands); Compose ≥2.24 note with empty-`.env` fallback; demo-case section rewritten to the *actual* frozen outcomes (Case 1 MINIMAL + eGFR-25 live tip, Case 2 with sertraline+ibuprofen instead of the impossible triple-whammy claim, Case 3 with STOPP/START findings); repository tree updated (tests/, scripts/, .github/, .streamlit/, pyproject); known-limitations note.
- **CI:** `.github/workflows/ci.yml` — setup-python 3.11 with pip cache → `ruff check .` → `pytest -q` (fully offline by design) → `python scripts/smoke_check.py`.

**Final verification (all green):** `ruff check .` 0 findings · `pytest -q` 73 passed · `smoke_check.py` exit 0 · compose configs validate (Phase 4) · UI click-through (Phases 3/5).

**Security audit (pre-push):** `.env` absent from entire git history and index · key-pattern grep matches only literal `"not-needed"` placeholders · `.gitignore` + `.dockerignore` both cover `.env` · no credentials in any tracked file.

**Outstanding (needs user):** ~~Fireworks live preflight~~ — **DONE in Phase 7** (see below).

---

## Phase 7 — Fireworks live verification + report-model fix — ✅

**Trigger:** user supplied a real FIREWORKS_API_KEY and asked to verify the live API.

**What the live check found:**
- Key authenticates and connectivity is fine.
- The configured `gemma-4-31b-it` (and every Gemma/Llama id) returns **404 "not deployed"** on this Fireworks account — no Gemma model is available. Account serves only: `deepseek-v4-pro`, `glm-5p1`, `glm-5p2`, `kimi-k2p6`, `gpt-oss-120b`, `flux-1-schnell`.
- These are **reasoning models** that emit hidden chain-of-thought; with `max_tokens=2048` the report JSON was intermittently truncated → silent fallback (patient summary worked, structured report didn't).

**What was fixed (user chose deepseek-v4-pro):**
- `config.py`: `GEMMA_MODEL` → **`REPORT_MODEL`** (back-compat alias kept), default now `deepseek-v4-pro`; added `REPORT_JSON_MODE` (Fireworks structured-JSON mode, forces a clean object from reasoning models) and `REPORT_MAX_TOKENS=4096` (headroom so reasoning + JSON both fit).
- `report_generator.py`: report call uses `REPORT_MODEL`, passes `response_format={"type":"json_object"}`, and the larger token budget.
- `fireworks_live_check.py`: model validation now does a real mini-completion (authoritative) instead of the `/models`-list membership check (which false-negatives on served models).
- **Honest relabeling:** the cloud layer is no longer branded "Gemma 4" (it isn't Gemma on this account). MedGemma 4B + TxGemma 2B on the AMD pod remain the real Gemma-on-AMD story. UI header chip shows the actual configured model dynamically; sidebar toggle → "Cloud AI reports"; footer/README/architecture updated. `.env`/`.env.example` use `REPORT_MODEL`.

**Verification evidence:** `ruff` clean · `pytest -q` 73 passed · `scripts\fireworks_live_check.py` **exit 0** with a genuinely live report (LLM summary, AI score 90/100, 4 deprescribing suggestions, 7 recommendations); report path run 3× → LIVE 3/3 (no fallback), 0 errors.

**Note for demo day:** the live AI report now works on the provided Fireworks account. If you switch accounts, run `python scripts\fireworks_live_check.py` to confirm `REPORT_MODEL` is served (it prints the account's available models on failure). The rule-based fallback still keeps the app functional if the API is ever down.

---

## Verification evidence log

- **2026-07-11 — Push + CI:** 8 commits pushed (`5e94627..439de4e`). GitHub Actions run **29147940833** GREEN — Install ✓, ruff ✓, pytest (73 offline) ✓, demo-case smoke check ✓. https://github.com/Vishwazeer/DrugLens/actions/runs/29147940833
- **2026-07-11 — Security audit:** `.env` absent from full git history & index; no key-pattern matches beyond literal `"not-needed"` placeholders; `.gitignore`/`.dockerignore` cover `.env`.
- **2026-07-11 — Final local gates:** `ruff check .` clean · `pytest -q` 73 passed · `scripts\smoke_check.py` exit 0 (MINIMAL/MODERATE/HIGH) · compose profiles validate without `.env` · live browser click-through of redesigned UI (Cases 1 & 3, all tabs, eGFR-25 renal demo) with 0 console errors.
