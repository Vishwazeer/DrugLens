# 💊 DrugLens — AI-Powered Geriatric Polypharmacy Safety Auditor

<p align="center">
  <img src="Assets/Generated output dashboard.png" alt="DrugLens Dashboard" width="900"/>
</p>

<p align="center">
  <strong>Clinical Decision Support for Safer Prescribing in Elderly Patients</strong><br/>
  <em>Deterministic Clinical Rules + AI Synthesis on AMD Instinct GPUs</em>
</p>

<p align="center">
  <a href="#-demo-video">🎬 Demo</a> •
  <a href="#-features">✨ Features</a> •
  <a href="#-architecture">🏗️ Architecture</a> •
  <a href="#-quick-start">🚀 Quick Start</a> •
  <a href="#-tech-stack">🔧 Tech Stack</a> •
  <a href="#-clinical-rulesets">📋 Clinical Rulesets</a>
</p>

---

## 🎬 Demo Video

https://github.com/user-attachments/assets/demo-video.mp4

> *Full walkthrough: Patient context setup → Analysis → Drug Interactions → Beers Criteria → STOPP/START → AI Narrative Streaming → Export → AI Prescribing Alternatives*

---

## 🧠 Problem Statement

**Polypharmacy in the elderly is a silent epidemic:**

- **40%+** of adults aged 65+ take **5 or more** prescription medications daily
- **3.5 million** doctor visits and **125,000 hospitalizations** annually from adverse drug events (ADEs)
- **$3.5 billion+** in avoidable emergency care costs per year
- Aging kidneys and liver metabolize drugs differently — standard dosing becomes dangerous

**Current EHR systems fail because:**
- ❌ **Alert fatigue** — checkers flag everything, doctors ignore 90% of warnings
- ❌ **Age-blind** — standard interactions ignore patient age, eGFR, or comorbidities
- ❌ **Unstructured text** — medication lists exist as free-text clinical notes, not clean tables
- ❌ **Novel drug blindspots** — lookup databases miss newly launched drug combinations

---

## ✨ Features

### 🔍 Intelligent Drug Interaction Detection
<p align="center">
  <img src="Assets/Drug-drug interaction.png" alt="Drug-Drug Interactions" width="700"/>
</p>

- Checks **all medication pairs** against a curated database of **200+ clinically significant drug-drug interactions**
- Severity-ranked results: **MAJOR** → MODERATE → MINOR
- Displays pharmacological mechanism, clinical effect, and management recommendations
- Covers critical combinations: warfarin + NSAIDs, opioids + benzodiazepines, triple whammy (ACE/ARB + diuretic + NSAID)

### ⚠️ AGS Beers Criteria 2023
<p align="center">
  <img src="Assets/Beers criteria.png" alt="Beers Criteria" width="700"/>
</p>

- Full implementation of the **American Geriatrics Society (AGS) Beers Criteria 2023** — the gold standard for identifying Potentially Inappropriate Medications (PIMs) in older adults
- **50+ evidence-based rules** across: Anticholinergics, CNS agents, Cardiovascular, Endocrine, GI, Pain/NSAIDs, Drug-Drug Interaction criteria
- Each flag includes: recommendation level, clinical rationale, quality of evidence, and strength of recommendation
- Age-aware and condition-aware matching

### 🔄 STOPP/START Criteria v3
<p align="center">
  <img src="Assets/Stopp-start criteria.png" alt="STOPP/START Criteria" width="700"/>
</p>

- **STOPP** (Screening Tool of Older Persons' Prescriptions): Identifies medications the patient IS taking that **should be stopped**
- **START** (Screening Tool to Alert to Right Treatment): Identifies medications the patient is NOT taking that **should be started**
- Split-view layout for instant clinical decision-making
- Based on STOPP/START v3 (2023), covering Cardiovascular, CNS, Renal, GI, Respiratory, Musculoskeletal, and Endocrine systems

### 🤖 AI Prescribing Alternatives
<p align="center">
  <img src="Assets/AI Prescribing Alternatives.png" alt="AI Prescribing Alternatives" width="700"/>
</p>

- For each flagged medication, the AI suggests a **safer therapeutic alternative** with clinical rationale
- Powered by Gemma models running on **AMD Instinct MI300X GPUs** via Fireworks AI
- Structured JSON output with drug-to-replacement mapping
- Examples: Ibuprofen → Acetaminophen (avoids nephrotoxicity), Metoclopramide → Omeprazole (avoids Parkinson's worsening)

### 👤 Patient Context Panel
<p align="center">
  <img src="Assets/patients context.png" alt="Patient Context" width="300"/>
</p>

- Configurable **patient age**, **eGFR** (renal function), and **comorbidities**
- 20+ selectable conditions: Hypertension, Diabetes, Heart Failure, Atrial Fibrillation, COPD, GERD, Parkinson's, Dementia, and more
- All clinical rules are filtered through patient context for personalized risk assessment
- Three pre-built demo cases (Mild, Moderate, Severe) for instant testing

### 📊 AI Clinical Narrative
- **Streaming real-time** clinical letter generation ("Dear Colleague" format)
- Prioritizes the most dangerous issues first
- Provides specific dosage adjustments and monitoring recommendations
- Shows **hardware routing badge** confirming AMD MI300X GPU path

### 📄 PDF Export
- One-click export to clean, print-ready clinical audit document
- Automatically hides UI chrome (sidebars, input bar)
- Adds patient context header (Age, eGFR, Comorbidities, Risk Score)
- Page-break-safe card layouts

### 🧭 Navigation & Controls
<p align="center">
  <img src="Assets/Menu bar.png" alt="Navigation Menu" width="80"/>
</p>

- **Home**: Reset analysis state
- **Rules**: View engine statistics (interaction database size, Beers/STOPP rule counts)
- **Safety**: Risk methodology explanation
- **Export**: Print/PDF export

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    React Frontend (Vite)                     │
│         Patient Context  ←→  Analysis Dashboard             │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP/SSE
┌────────────────────────────▼────────────────────────────────┐
│                   FastAPI Backend (api.py)                   │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  /api/analyze │  │/api/narrative│  │/api/alternatives │  │
│  │  (sync JSON)  │  │  (SSE stream)│  │  (SSE stream)    │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│  ┌──────▼───────────────────────────────────────────────┐  │
│  │            Deterministic Rules Engine (src/)          │  │
│  │  • drug_interactions.py — 200+ DDI pairs              │  │
│  │  • drug_interactions.py — Beers 2023 (50+ rules)      │  │
│  │  • drug_interactions.py — STOPP/START v3              │  │
│  │  • router.py — LLM routing + fallback queue           │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                 │
│           ┌───────────────┼───────────────┐                 │
│           ▼               ▼               ▼                 │
│    ┌─────────────┐ ┌─────────────┐ ┌──────────────┐       │
│    │ MedGemma 4B │ │ TxGemma 2B  │ │ Gemma 4 31B  │       │
│    │ (Local vLLM)│ │ (Local vLLM)│ │(Fireworks AI) │       │
│    │ AMD MI300X  │ │ AMD MI300X  │ │ AMD MI300X    │       │
│    └─────────────┘ └─────────────┘ └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### Multi-Model Pipeline

| Model | Location | Purpose | Fallback |
|-------|----------|---------|----------|
| **MedGemma 4B** | Local AMD GPU (vLLM) | Parse unstructured clinical text into structured medication lists | Regex parser |
| **TxGemma 2B** | Local AMD GPU (vLLM) | Predict novel drug-drug interactions via SMILES molecular strings | Local DDI database |
| **Gemma 4 31B** | Fireworks AI Cloud (AMD MI300X) | Generate clinical narratives and prescribing alternatives | Template-based scoring |

### Resilient Fallback Design

The system degrades gracefully when GPU resources are unavailable:

1. **GPU Available** → Full AI pipeline (MedGemma parsing + TxGemma DDI + Gemma narrative)
2. **GPU Offline** → Deterministic rules engine (regex parsing + local DDI database + Beers/STOPP matching)
3. **Cloud Offline** → Local-only mode with template-based risk scoring

**Zero clinical safety rules are ever skipped** — the deterministic engine always runs regardless of AI availability.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- Fireworks AI API key (for cloud LLM features)

### Local Development

```bash
# Clone the repository
git clone https://github.com/Vishwazeer/DrugLens.git
cd DrugLens

# Set up environment
cp .env.example .env
# Edit .env and add your FIREWORKS_API_KEY

# Install Python dependencies
pip install -r requirements.txt

# Build the frontend
cd frontend
npm install
VITE_API_URL="" npm run build
cd ..

# Run the server
python api.py
# Open http://localhost:8000
```

### Docker Deployment

```bash
# Build and run with Docker Compose
docker-compose up --build

# Or build manually
docker build -t druglens .
docker run -p 8000:8000 --env-file .env druglens
```

### AMD GPU Pod (Hackathon)

```bash
# On AMD Instinct MI300X pod with ROCm + vLLM
git clone https://github.com/Vishwazeer/DrugLens.git
cd DrugLens
chmod +x setup_amd_pod.sh
./setup_amd_pod.sh
# Select Option 2: Native Python/vLLM
```

---

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS, Lucide Icons |
| **Backend** | Python 3.12, FastAPI, Uvicorn, SSE (Server-Sent Events) |
| **AI Models** | Google Gemma 4 31B, MedGemma 4B, TxGemma 2B |
| **GPU Runtime** | AMD ROCm, vLLM, AMD Instinct MI300X |
| **Cloud API** | Fireworks AI (AMD MI300X hosted inference) |
| **Drug APIs** | RxNorm (NIH), PubChem (SMILES lookup) |
| **Containerization** | Docker, Docker Compose |
| **CI/CD** | GitHub Actions |

---

## 📋 Clinical Rulesets

### Data Files

| File | Contents | Count |
|------|----------|-------|
| `data/beers_criteria.json` | AGS Beers Criteria 2023 PIMs | 50+ rules |
| `data/stopp_start.json` | STOPP/START v3 (2023) criteria | 40 STOPP + 20 START |
| `data/drug_interactions.json` | Curated drug-drug interaction pairs | 200+ pairs |
| `data/demo_cases.json` | Pre-built test cases (Mild/Moderate/Severe) | 3 cases |

### Clinical Evidence Sources

- **AGS Beers Criteria 2023** — American Geriatrics Society. *Updated AGS Beers Criteria for Potentially Inappropriate Medication Use in Older Adults.* J Am Geriatr Soc. 2023.
- **STOPP/START v3** — O'Mahony et al. *STOPP/START criteria for potentially inappropriate prescribing in older people: version 3.* Eur Geriatr Med. 2023. (CC BY 4.0)
- **Drug Interaction Database** — Curated from FDA labeling, clinical pharmacology references, and peer-reviewed interaction studies.

---

## 📁 Project Structure

```
DrugLens/
├── api.py                    # FastAPI server + static file hosting
├── src/
│   ├── __init__.py
│   ├── config.py             # Environment configuration
│   ├── drug_interactions.py  # DDI, Beers, STOPP/START matching engine
│   ├── router.py             # LLM routing with Gemma-priority fallbacks
│   └── schemas.py            # Pydantic request/response models
├── data/
│   ├── beers_criteria.json   # AGS Beers 2023 rules
│   ├── stopp_start.json      # STOPP/START v3 rules
│   ├── drug_interactions.json # 200+ DDI pairs
│   └── demo_cases.json       # Pre-built test cases
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # Main React application
│   │   └── index.css         # Global styles + print overrides
│   ├── package.json
│   └── vite.config.ts
├── scripts/
│   ├── smoke_check.py        # End-to-end pipeline validation
│   └── fireworks_live_check.py # API connectivity diagnostics
├── tests/                    # Test suite
├── Assets/                   # UI screenshots for documentation
├── Dockerfile                # Container build
├── docker-compose.yml        # Multi-service orchestration
├── setup_amd_pod.sh          # AMD GPU pod bootstrap script
├── requirements.txt          # Python dependencies
└── .env.example              # Environment variable template
```

---

## 🧪 Testing

```bash
# Run smoke check (validates all 3 demo cases end-to-end)
python scripts/smoke_check.py

# Expected output:
# Case 1: MINIMAL risk (0 interactions, 0 Beers flags)
# Case 2: MODERATE risk (2 interactions, 3 Beers flags, 1 STOPP)
# Case 3: HIGH risk (6 interactions, 7 Beers flags, 6 STOPP)
# SMOKE CHECK PASSED
```

---

## 🏆 AMD Developer Hackathon: Act II

**Track:** Unicorn Track  
**Team:** team-3103

### Why DrugLens Wins

| Criterion | How We Excel |
|-----------|-------------|
| **Creativity/Originality** | Only submission addressing geriatric polypharmacy — a $3.5B clinical problem |
| **Product/Market Potential** | 55M+ elderly Americans on 5+ drugs. Direct integration path into EHR systems |
| **Completeness** | Full-stack working prototype: deterministic rules + AI synthesis + export |
| **Use of AMD Platform** | Triple Gemma model pipeline on AMD Instinct MI300X via Fireworks AI + local vLLM |

---

## 📄 License

This project was built for the AMD Developer Hackathon: Act II. Clinical rulesets are based on published medical guidelines (AGS Beers Criteria 2023, STOPP/START v3 CC BY 4.0).

---

<p align="center">
  <strong>DrugLens</strong> — Because every prescription deserves a second look. 💊
</p>
