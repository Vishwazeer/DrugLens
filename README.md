# 💊 DrugLens — AI-Powered Geriatric Polypharmacy Risk Analyzer

> **AMD Developer Hackathon: ACT II — Track 3 (Unicorn Track)**  
> An advanced clinical decision support tool designed to identify medication risks, drug-drug interactions, Beers Criteria violations, and STOPP/START mismatches in elderly patients using a multi-model Gemma pipeline.

---

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react" alt="React">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/AMD-Instinct%20GPUs-ED1C24?style=for-the-badge&logo=amd" alt="AMD">
  <img src="https://img.shields.io/badge/Google-Gemma%20Suite-4285F4?style=for-the-badge&logo=google" alt="Gemma">
  <img src="https://img.shields.io/badge/ROCm-Compatible-0052CC?style=for-the-badge" alt="ROCm">
</p>

---

## 🎯 The Geriatric Polypharmacy Crisis

Older adults (aged 65+) represent 16% of the US population but consume over **30% of all prescription medications**. 
* **Polypharmacy** (taking 5+ medications daily) affects over **40% of seniors**.
* Adverse Drug Events (ADEs) in the elderly lead to **3.5 million physician office visits** and **125,000 hospitalizations** annually.
* Most of these events are preventable, resulting from known drug-drug interactions or age-inappropriate prescribing.

**DrugLens** provides clinicians with an instant, structured audit of complex geriatric medication regimens, matching them against gold-standard clinical rulesets while leveraging local Gemma models (on AMD hardware) to parse text and predict structural interactions, plus a cloud model to write the clinical safety report.

---

## 🏗️ Multi-Model Architecture

DrugLens runs **Gemma where it matters most — on AMD hardware**: MedGemma 4B and TxGemma 2B execute locally on an AMD Instinct GPU (vLLM + ROCm) for private, on-prem clinical parsing and interaction prediction (the AMD-hosted Gemma story). A third, **configurable cloud model** on Fireworks AI handles the final narrative report synthesis. The pipeline degrades gracefully at every tier, so it runs end-to-end on CPU with no GPU at all.

```
                  ┌────────────────────────────────────────┐
                  │           Clinician Input              │
                  │   (Free-text notes or prescription)   │
                  └───────────────────┬────────────────────┘
                                      │
                                      ▼
                  ┌────────────────────────────────────────┐
                  │       [Model 1] MedGemma 4B            │  ◄── (Local AMD GPU / vLLM)
                  │       Parses notes -> Structured JSON  │
                  └───────────────────┬────────────────────┘
                                      │
                                      ▼
                  ┌────────────────────────────────────────┐
                  │            Analysis Engine             │
                  │  Matches local DBs, Beers, STOPP/START │
                  └───────────────────┬────────────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
┌───────────────────────────┐                   ┌───────────────────────────┐
│   [Model 2] TxGemma 2B    │                   │  [Model 3] Cloud Report   │
│  Predicts novel DDIs from │                   │ Generates final clinical  │
│  molecular SMILES strings │                   │ report & patient summary  │
└───────────────────────────┘                   └───────────────────────────┘
 ◄── (Local AMD GPU / vLLM)                      ◄── (Fireworks AI / AMD)
```

1. **MedGemma 4B-IT (Local on AMD Instinct GPU / vLLM + ROCm)**
   * **Role**: Clinical parsing. Extracts medication names, dosages, route, and frequency from raw, unstructured clinical entry notes.
2. **TxGemma 2B (Local on AMD Instinct GPU / vLLM + ROCm)**
   * **Role**: Therapeutic interaction prediction. For drug pairs not present in our verified database, TxGemma resolves their molecular SMILES structures via PubChem and predicts potential structural interactions.
3. **Cloud Report Model (Remote API via Fireworks AI on AMD Infrastructure)**
   * **Role**: Report orchestration and synthesis. Reviews the compiled list of interactions, Beers alerts, and STOPP/START flags to generate a professional clinical safety report and a simplified patient-friendly summary.
   * **Model-agnostic**: set `REPORT_MODEL` to any chat model your Fireworks account serves (verify with `python scripts/fireworks_live_check.py`). Reasoning models are supported via Fireworks JSON mode (`REPORT_JSON_MODE=true`).

---

## 📜 Clinical Foundations Included

DrugLens is built on top of digitized versions of the most trusted geriatric pharmacology guidelines:

### 1. AGS Beers Criteria (2023 Update)
A guideline from the American Geriatrics Society cataloging Potentially Inappropriate Medications (PIMs) that older adults should avoid or use with caution. DrugLens includes a digitized index of **50+ high-risk PIM classes** (anticholinergics, long-acting sulfonylureas, skeletal muscle relaxants, high-dose digoxin).

### 2. STOPP/START Criteria (Version 3, 2023)
* **STOPP** (Screening Tool of Older Persons' Prescriptions): Identifies medications that should be discontinued (e.g., PPIs long-term without indication, duplicate drug classes, benzodiazepines in patients with a history of falls).
* **START** (Screening Tool to Alert to Right Treatment): Suggests crucial medications that should be initiated based on the patient's underlying conditions (e.g., Statins for secondary cardiovascular prevention, ACE-inhibitors in heart failure).

---

## 🔌 Graceful Fallback Architecture

To ensure the application remains operational in resource-constrained environments (or when local GPUs are offline), DrugLens is built with a **resilient multi-tier fallback architecture**:

| Feature | Primary AI Engine (GPU) | Graceful Fallback (CPU-only / API) |
|---------|-------------------------|------------------------------------|
| **Medication Parsing** | **MedGemma 4B** (Local vLLM) parses messy prescriptions | **Structured Regex Engine** splits and matches standard dosages |
| **DDI Checking** | **TxGemma 2B** predicts novel interactions from molecular SMILES | **Verified Local DB** check (100+ clinical pairs indexed) |
| **Risk Report** | **Cloud model** (Fireworks) writes custom clinical analysis | **Rule-Based Engine** compiles score & fills structured template |

---

## 🚀 Step-by-Step Walkthrough

### 1. Local Run (CPU-Only / API Mode)

The app is a **React (Vite + TypeScript + Tailwind) frontend** talking to a **FastAPI backend** that wraps the deterministic engine and escalates complex cases to the Fireworks cloud model. **Requires Python ≥ 3.10 and Node ≥ 20.**

```bash
# Clone the repository
git clone https://github.com/Vishwazeer/DrugLens.git
cd DrugLens

# Backend deps + config
pip install -r requirements.txt
cp .env.example .env
# Edit .env and insert your: FIREWORKS_API_KEY=your_key_here

# Terminal 1 — API on :8000
uvicorn api:app --reload --port 8000

# Terminal 2 — React UI on :5173
cd frontend && npm install && npm run dev
```

Open the Vite URL (http://localhost:5173). The UI calls the API on `:8000`.

**Single-origin build** (one server for API + UI, as used in Docker):

```bash
cd frontend && VITE_API_URL="" npm run build && cd ..
uvicorn api:app --port 8000     # serves the built UI at / and the API at /api/*
```

**API endpoints:** `POST /api/analyze` · `POST /api/analyze/stream-narrative` (SSE) · `POST /api/analyze/alternatives` · `GET /api/demo-cases` · `GET /api/conditions` · `GET /api/health`

### Testing & Quality Gates

The deterministic pipeline is covered by a fully offline pytest suite (network calls are hard-blocked in tests) plus an assertive smoke check that freezes the three demo cases' expected outcomes. CI (GitHub Actions) runs ruff + pytest + the smoke check on every push.

```bash
pip install -r requirements-dev.txt

ruff check .                            # lint — expect zero findings
pytest -q                               # 75 offline tests
python scripts/smoke_check.py           # demo cases hit their risk bands (exit code gated)
python scripts/fireworks_live_check.py  # live preflight: API key + model id + end-to-end report
```

### 2. AMD GPU Pod Setup (Full 3-Model Pipeline)

When you deploy your AMD Instinct GPU pod on the AMD Developer Cloud:

```bash
# SSH into your pod, clone, and configure
git clone https://github.com/Vishwazeer/DrugLens.git
cd DrugLens

# Create .env with Hugging Face Token (needed for gated MedGemma/TxGemma models)
echo "HF_TOKEN=your_huggingface_read_token" > .env
# Also add your Fireworks key for reports:
echo "FIREWORKS_API_KEY=your_fireworks_key" >> .env

# Make setup script executable and run it
chmod +x setup_amd_pod.sh
./setup_amd_pod.sh
```

Select **Option 2 (Native Python/vLLM)** when prompted. The script will automatically:
1. Verify GPU availability with `rocm-smi`.
2. Install `vllm` and authenticate with Hugging Face.
3. Launch **MedGemma** on port `8001` and **TxGemma** on port `8002` in the background.

---

## 🐳 Docker Deployment

We provide ready-to-use Docker compose profiles for different setups.

### CPU / API Mode (No local GPU needed)
```bash
docker compose --profile cpu-only up --build
```
*Port exposed: `8000` — one container serves the API and the built React UI on the same origin. A `.env` file is optional (Docker Compose ≥ 2.24 — on older Compose versions create an empty `.env` first).*

### Full GPU Mode (MedGemma + TxGemma + App served locally on ROCm)
```bash
docker compose --profile gpu up --build
```
*Note: Requires AMD GPU pass-through capability inside Docker. The app container in this profile enables the MedGemma/TxGemma toggles by default.*

---

## 🧪 Interactive Demo Cases

To help judges evaluate the application immediately, the sidebar contains three pre-loaded clinical scenarios (their outcomes are frozen by the test suite — `tests/test_demo_cases.py`):

* **Case 1 — Mild (MINIMAL risk)**: A 70yo patient on metformin, lisinopril, and amlodipine. Zero interactions, zero Beers/STOPP alerts — the system stays quiet for a safe regimen instead of crying wolf. **Live demo tip:** lower the eGFR input to 25 and re-analyze — the renal safety rules (metformin lactic-acidosis PIM, STOPP-E2) activate in real time.
* **Case 2 — Moderate (MODERATE risk)**: A 78yo patient on omeprazole, ibuprofen, lisinopril, sertraline, and acetaminophen. Triggers:
  * NSAID + ACE inhibitor interaction (acute kidney injury risk, major).
  * Sertraline + ibuprofen interaction (GI bleeding risk, moderate).
  * Beers warnings for long-term PPI use and chronic NSAID use in the elderly.
* **Case 3 — Severe (HIGH risk)**: An 85yo patient on 8 medications (warfarin, digoxin, amiodarone, lorazepam, oxycodone, diphenhydramine, furosemide, KCl). Triggers:
  * 6 major interactions, including Warfarin ↔ Amiodarone and Digoxin ↔ Amiodarone.
  * FDA Black Box: Opioid (oxycodone) + Benzodiazepine (lorazepam) respiratory depression.
  * Beers: benzodiazepine in the elderly, first-generation antihistamine, ≥3 concurrent CNS-active drugs.
  * STOPP: opioid + benzodiazepine combination, opioid without laxative prophylaxis.
  * START: guideline-directed heart-failure therapy (ACE inhibitor, beta-blocker) flagged as missing.

---

## 📁 Repository Structure

```
DrugLens/
├── api.py                  # FastAPI backend (analyze, SSE narrative, alternatives)
├── frontend/               # React + Vite + TypeScript + Tailwind UI
├── setup_amd_pod.sh        # Automates ROCm + vLLM model deployments
├── Dockerfile              # Multi-stage: builds React, serves it from FastAPI
├── docker-compose.yml      # gpu / cpu-only profiles
├── pyproject.toml          # pytest + ruff config, requires-python >= 3.10
├── requirements.txt        # Runtime dependencies
├── requirements-dev.txt    # pytest + ruff
├── PROGRESS.md             # Per-phase implementation & verification log
├── .github/workflows/ci.yml  # CI: ruff + pytest + smoke check
├── data/
│   ├── beers_criteria.json     # AGS Beers 2023 PIMs (combination/eGFR-gated rules)
│   ├── stopp_start.json        # STOPP/START v3 rules (combination/eGFR/absence gates)
│   └── drug_interactions.json  # Curated index of 100+ clinical DDIs (deduplicated)
├── src/
│   ├── config.py               # Single source of settings (endpoints, key, flags)
│   ├── drug_interactions.py    # Deterministic rules engine (DDI/Beers/STOPP/START)
│   ├── med_parser.py           # MedGemma parser + regex fallback
│   ├── ddi_predictor.py        # TxGemma SMILES-based predictor
│   ├── report_generator.py     # Cloud report (Fireworks) + rule-based fallback
│   ├── router.py               # Token-efficient edge/cloud routing + SSE streaming
│   └── analyzer.py             # Orchestrator pipeline + risk scoring
├── scripts/
│   ├── smoke_check.py          # Offline demo-case assertion script
│   └── fireworks_live_check.py # Live Fireworks preflight (key + model id + report)
└── tests/                  # 75 offline pytest tests (engines, parser, pipeline, demos)
```

**Known limitations / future work:** duplicate drug-class detection (former STOPP-Q1) is not implemented; combination products (e.g. Percocet) map to their opioid component only; local vLLM code paths are unit-tested with mocks (verify on an AMD pod before GPU demos).

---

## ⚠️ Disclaimer

DrugLens is for **educational, demonstration, and research purposes only**. It is not a certified diagnostic tool or a substitute for professional clinical judgment. Always consult a licensed medical professional before making adjustments to any medication regimen.
