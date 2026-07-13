<div align="center">

# DrugLens

**Geriatric Polypharmacy Safety Auditor — Catches What EHR Alert Systems Miss**

*A deterministic clinical rules engine that runs on every request in ~3 ms, escalating to a cloud model only when the case actually warrants it.*

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?style=flat&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-Source%20Available-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-75%20passing-brightgreen)](tests/)

[**Live Demo →**](http://172.105.40.61:8000)&nbsp;&nbsp;|&nbsp;&nbsp;[**Deployment →**](DEPLOYMENT.md)&nbsp;&nbsp;|&nbsp;&nbsp;[**Problem Statement →**](PROBLEM_STATEMENT.md)&nbsp;&nbsp;|&nbsp;&nbsp;[**Build Log →**](PROGRESS.md)

</div>

---

## Overview

Polypharmacy — five or more daily prescriptions — is now the norm in elderly care, and it is dangerous. Adverse drug events drive roughly **30% of emergency hospital admissions** in adults over 65 and about **$3.5 billion** in avoidable US spend each year. Existing EHR checkers make this worse rather than better: they flag every theoretical drug pair regardless of context, so clinicians mute or ignore up to **90% of warnings** and real hazards get lost in the noise.

DrugLens attacks the problem from the precision side instead of the volume side. A deterministic engine — 102 curated drug-drug interactions, 61 AGS Beers Criteria 2023 rules, 38 STOPP + 20 START v3 criteria — runs on **every** request, gated on the patient's actual age, eGFR and comorbidities. Only cases that score MODERATE or HIGH are escalated to a cloud model for narrative synthesis and prescribing alternatives. Safe patients are answered entirely offline, for **zero LLM tokens**.

**What makes this different from typical drug-checker demos:**

- **True combination-rule logic** — "opioid **+** benzodiazepine" and the renal "triple whammy" fire only when *every* component is present, never on a single drug. Implemented as AND-semantics over `combination_groups` / `min_matches` and locked by tests. Naive engines get this wrong and drown clinicians in false positives.
- **eGFR-gated renal rules** — metformin, NSAID and digoxin alerts activate only below their real renal thresholds. Change one field in the UI and watch them turn on.
- **The rules can never be skipped or hallucinated** — the deterministic engine always runs first; the LLM only *narrates* findings it cannot invent or suppress.
- **Novel-drug coverage** — pairs with no database entry are evaluated by the cloud model grounded in each drug's PubChem SMILES structure, catching interactions no lookup table contains.
- **Every number in the UI is measured, not asserted** — ruleset counts and engine latency are read live from `GET /api/engine-stats`, so they always match `data/*.json`.

---

## Architecture

```
  Free-text clinical note  OR  structured medication list
                    |
                    v
  +---------------------------------+
  |  Clinical Text Parser            |  drug-vocabulary anchored;
  |  src/med_parser.py               |  lifts age / eGFR / conditions
  +----------------+-----------------+
                   |
                   v
  +---------------------------------+
  |  Deterministic Rules Engine      |  ALWAYS RUNS -- ~3 ms, 0 tokens
  |  src/drug_interactions.py        |
  |    - 102 curated DDI pairs        |  combination-aware (AND-logic)
  |    - 61 Beers Criteria 2023       |  age- and eGFR-gated
  |    - 38 STOPP + 20 START v3       |  condition-gated
  +----------------+-----------------+
                   |
                   +--> LOW / MINIMAL risk --> answered here. 0 LLM tokens.
                   |
                   v
  +---------------------------------+
  |  Token-Efficient Router          |  escalate MODERATE / HIGH only
  |  src/router.py                   |
  +----------------+-----------------+
                   |
         +---------+---------+
         v                   v
  +--------------+   +------------------+
  | Novel DDI    |   |  Cloud Model     |
  | Prediction   |   |  (Fireworks AI)  |
  | PubChem      |   |                  |
  | SMILES       |   |                  |
  +------+-------+   +--------+---------+
         |                    |
         +---------+----------+
                   v
  +---------------------------------+
  |  Clinical Report                 |  streaming narrative,
  |  + PDF export                    |  deprescribing suggestions,
  +---------------------------------+  safer alternatives
```

The API and the built React UI are served by a **single** uvicorn process on one origin — no CORS surface, no second web server.

### Honest scope

Being precise about this is worth more than a bigger-sounding claim.

| Component | Status |
|---------|--------|
| **Deterministic clinical engine** (102 DDI / 61 Beers / 38 STOPP + 20 START) | **Live.** Runs on every request, before and independently of any LLM. Median **~3 ms** — measured, exposed at `GET /api/engine-stats`. |
| **Token-efficient routing** | **Live.** Two of the three demo cases never invoke a GPU at all. |
| **Cloud synthesis** — streaming narrative, JSON prescribing alternatives, novel-DDI prediction | **Live**, via Fireworks AI (`deepseek-v4-pro`, configurable). |
| **MedGemma 4B / TxGemma 2B on AMD Instinct (vLLM + ROCm)** | **Code-complete but NOT enabled.** The public demo runs on a CPU-only VM. The GPU path ships and is reviewable (`docker compose --profile gpu`, `setup_amd_pod.sh`) but we had no MI300X access, so it is **unbenchmarked and we make no performance claim for it**. |

---

## Features

| Feature | Detail |
|---------|--------|
| **Drug-drug interaction detection** | All medication pairs checked against 102 curated interactions, severity-ranked MAJOR → MODERATE → MINOR, each with mechanism, clinical effect and management guidance |
| **Combination-rule AND-semantics** | Multi-drug hazards (opioid + benzodiazepine, ACE/ARB + diuretic + NSAID) fire only when every component is present — the core defence against alert fatigue |
| **AGS Beers Criteria 2023** | 61 rules identifying Potentially Inappropriate Medications in older adults, each gated on age and comorbidity, with rationale and quality of evidence |
| **STOPP/START v3** | 38 STOPP rules (drugs that should be stopped) and 20 START rules (therapies that should be started), in a split-view clinical layout |
| **eGFR-driven renal gating** | Renal alerts activate only below their true eGFR thresholds — metformin is silent at eGFR 90 and flagged at eGFR 25 |
| **Unstructured note parsing** | Reads free-text clinical prose, anchoring drug names against the engine's own vocabulary and lifting age, eGFR, conditions and allergies out of the note |
| **Novel-DDI prediction** | Drug pairs with no database entry are evaluated by the cloud model, grounded in PubChem SMILES structures, surfacing interactions no lookup table contains |
| **Token-efficient routing** | LOW and MINIMAL cases are answered entirely by the offline engine for zero LLM tokens; a routing badge in the UI shows which path was taken |
| **Streaming clinical narrative** | Real-time "Dear Colleague" clinical letter, worst hazards first, with specific dosage and monitoring recommendations |
| **AI prescribing alternatives** | For each flagged medication, a safer therapeutic substitute with clinical rationale, returned as structured JSON |
| **Print-ready PDF export** | One-click clinical audit document with patient-context header and medical disclaimer; UI chrome and browser headers suppressed |
| **Live engine statistics** | Ruleset counts and engine latency read from the loaded rules and measured at request time — never hardcoded |

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 19, TypeScript 5.6, Vite, Tailwind CSS | Clinical instrument panel UI, streaming result rendering, PDF export |
| **Backend** | Python 3.12, FastAPI, Uvicorn | JSON + SSE API; also serves the built frontend from one origin |
| **Rules engine** | Pure Python, no framework | 102 DDI / 61 Beers / 58 STOPP-START rules with AND-semantics, age, condition and eGFR gates |
| **Cloud inference** | Fireworks AI (`deepseek-v4-pro`, configurable) | Clinical narrative, prescribing alternatives, novel-DDI prediction |
| **Chemistry lookup** | PubChem PUG REST | SMILES structures used to ground novel-DDI prediction |
| **GPU path** *(shipped, not enabled)* | AMD ROCm + vLLM | MedGemma 4B parsing, TxGemma 2B DDI prediction |
| **Containerization** | Docker, Docker Compose | `cpu-only` and `gpu` profiles |
| **Testing** | pytest, ruff | 75 offline tests, network-blocked; lint and format gates |
| **CI/CD** | GitHub Actions | ruff → pytest → demo-case smoke check → frontend typecheck and build |

---

## Project Structure

```
DrugLens/
+-- api.py                       # FastAPI server; serves API + built frontend
+-- src/
|   +-- config.py                # Environment configuration
|   +-- med_parser.py            # Free-text clinical note parser
|   +-- drug_interactions.py     # DDI / Beers / STOPP-START matching engine
|   +-- analyzer.py              # Orchestrator, risk scoring, routing decision
|   +-- ddi_predictor.py         # Novel-DDI prediction (PubChem SMILES)
|   +-- report_generator.py      # Clinical narrative + prescribing alternatives
|   +-- router.py                # Cloud model routing with fallback queue
+-- data/
|   +-- drug_interactions.json   # 102 curated DDI pairs
|   +-- beers_criteria.json      # 61 AGS Beers 2023 rules
|   +-- stopp_start.json         # 38 STOPP + 20 START v3 criteria
+-- frontend/
|   +-- src/App.tsx              # Main React application
|   +-- src/index.css            # Global styles + print overrides
|   +-- vite.config.ts
+-- deploy/
|   +-- server/                  # Linode deploy script + systemd unit
|   +-- hf-space/                # Hugging Face Space packaging
+-- scripts/
|   +-- smoke_check.py           # End-to-end demo-case validation
|   +-- fireworks_live_check.py  # Cloud API connectivity diagnostics
+-- tests/                       # 75 offline tests (network-blocked)
+-- Assets/                      # UI screenshots
+-- Dockerfile
+-- docker-compose.yml           # cpu-only / gpu profiles
+-- setup_amd_pod.sh             # AMD GPU pod bootstrap
+-- DEPLOYMENT.md                # Production deployment runbook
+-- PROBLEM_STATEMENT.md         # Clinical problem and how each failure is answered
+-- PROGRESS.md                  # Phase-by-phase build log
```

---

## Quick Start

### Prerequisites
- Python 3.10 or newer
- Node.js 18 or newer
- A Fireworks AI API key — [free signup](https://fireworks.ai/) (optional; the deterministic engine runs without it)

### 1. Clone and install

```bash
git clone https://github.com/Vishwazeer/DrugLens.git
cd DrugLens
pip install -r requirements.txt
```

### 2. Configure secrets

```bash
cp .env.example .env
# Edit .env and set FIREWORKS_API_KEY
```

### 3. Build the frontend

```bash
cd frontend
npm install
VITE_API_URL="" npm run build
cd ..
```

### 4. Run

```bash
python api.py
# Open http://localhost:8000
```

Or with Docker:

```bash
docker compose --profile cpu-only up --build     # app only
docker compose --profile gpu up --build          # adds MedGemma + TxGemma on vLLM/ROCm
```

### 5. Use it

1. Load **Case 1** and analyse — it stays quiet. No false alarms on a safe regimen.
2. Set **eGFR to 25** and re-run — the renal safety rules activate live.
3. Load **Case 3** and watch the cloud narrative stream in, then export the PDF.
4. Paste a free-text clinical note instead of a medication list — the parser reads it directly.

---

## Running Tests

```bash
pytest -q                        # 75 offline tests, network-blocked
ruff check .                     # lint gate
python scripts/smoke_check.py    # end-to-end demo-case validation
```

Expected smoke output:

```
Case 1: MINIMAL risk (0 interactions, 0 Beers flags)
Case 2: MODERATE risk (2 interactions, 3 Beers flags, 1 STOPP)
Case 3: HIGH risk (6 interactions, 7 Beers flags, 6 STOPP)
SMOKE CHECK PASSED
```

CI runs ruff, pytest, the smoke check, and a frontend typecheck and production build on every push.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `FIREWORKS_API_KEY` | *(none)* | Cloud inference key. Without it the deterministic engine still runs and rule-based fallbacks are used. |
| `REPORT_MODEL` | `accounts/fireworks/models/deepseek-v4-pro` | Cloud model id for narrative and alternatives. |
| `REPORT_MODEL_FALLBACKS` | *(empty)* | Comma-separated model ids tried *before* `REPORT_MODEL`. The first that works is cached, so a preferred model can be trialled without risking the demo. |
| `REPORT_JSON_MODE` | `true` | Forces structured-JSON responses. Keep enabled — reasoning models otherwise emit chain-of-thought and break parsing. |
| `REPORT_MAX_TOKENS` | `4096` | Output budget. Reasoning models spend a large, variable share on hidden reasoning; a smaller budget truncates the result. |
| `USE_GEMMA4` | `true` | Enable cloud report generation. |
| `USE_LLM_PARSER` | `false` | MedGemma parsing via local vLLM. Leave off on CPU hosts. |
| `USE_TXGEMMA` | `false` | TxGemma DDI prediction via local vLLM. Leave off on CPU hosts. |

---

## Security

| Control | Implementation |
|---------|----------------|
| **Secret handling** | API keys are read from the environment only. `.env` is gitignored and excluded from Docker images via `.dockerignore`. No key is ever logged or returned by the API. |
| **Process isolation** | In production DrugLens runs as its own unprivileged system user with no sudo rights, in its own directory, on its own port. |
| **Resource containment** | The systemd unit caps the service at `MemoryMax=512M` and `CPUQuota=70%`, so it cannot starve anything co-hosted on the box. |
| **Secret file permissions** | The production env file is mode `640`, owned `root:service-user` — unreadable by other accounts on the host. |
| **Network exposure** | A single port is bound. Two stacked firewalls (cloud firewall + host `ufw`) govern ingress. |
| **Offline test suite** | `tests/conftest.py` blocks all outbound network calls, so CI can never leak a key or depend on a live endpoint. |
| **Non-root container** | The Docker image runs as uid 1000, not root. |

Full production hardening and the deployment runbook are documented in [DEPLOYMENT.md](DEPLOYMENT.md).

---

## Screenshots

<div align="center">

**Analysis dashboard**

<img src="Assets/Generated output dashboard.png" alt="DrugLens dashboard" width="850"/>

**Drug-drug interactions**

<img src="Assets/Drug-drug interaction.png" alt="Drug-drug interactions" width="700"/>

**AGS Beers Criteria 2023**

<img src="Assets/Beers criteria.png" alt="Beers Criteria" width="700"/>

**STOPP/START v3**

<img src="Assets/Stopp-start criteria.png" alt="STOPP/START criteria" width="700"/>

**AI prescribing alternatives**

<img src="Assets/AI Prescribing Alternatives.png" alt="AI prescribing alternatives" width="700"/>

</div>

A full walkthrough is in the [Demo Video](https://drive.google.com/file/d/1ld5lxCGfChBpa6zPNzkhn6Hm7w7WhrIw/view?usp=sharing).

---

## Clinical Evidence Sources

- **AGS Beers Criteria 2023** — American Geriatrics Society. *Updated AGS Beers Criteria for Potentially Inappropriate Medication Use in Older Adults.* J Am Geriatr Soc. 2023.
- **STOPP/START v3** — O'Mahony et al. *STOPP/START criteria for potentially inappropriate prescribing in older people: version 3.* Eur Geriatr Med. 2023. (CC BY 4.0)
- **Drug interaction database** — curated from FDA labeling, clinical pharmacology references, and peer-reviewed interaction studies.

> **Medical disclaimer.** DrugLens is a decision-support prototype built for a hackathon. It is not a medical device, has not been clinically validated, and must not be used to make real prescribing decisions.

---

## License

**Source Available — All Rights Reserved.** See [LICENSE](LICENSE) for full terms.

The source code is publicly visible for viewing and educational purposes. Any use in personal, commercial, or academic projects requires explicit written permission from the author.

To request permission: navnitamrutharaj1234@gmail.com

**Author:** Navnit Amrutharaj
