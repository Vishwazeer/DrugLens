# 💊 DrugLens — AI-Powered Polypharmacy Risk Analyzer

> Paste a patient's medication list → get instant drug interaction analysis, Beers Criteria alerts, STOPP/START recommendations, and AI-generated deprescribing suggestions.

**Built for AMD Developer Hackathon: ACT II — Track 3 (Unicorn Track)**

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.45-red)
![AMD](https://img.shields.io/badge/AMD-Developer%20Cloud-ed1c24)
![Gemma](https://img.shields.io/badge/Google-Gemma-4285F4)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 🎯 Problem

**40% of seniors take 5+ medications.** Adverse drug events in the elderly cost **$3.5 billion/year** in the US alone. Most are preventable — but checking every drug interaction, age-appropriateness criterion, and deprescribing opportunity manually is time-consuming and error-prone.

## 💡 Solution

**DrugLens** is an AI-powered clinical decision support tool that instantly analyzes a patient's medication regimen and surfaces:

- ⚠️ **Drug-Drug Interactions** — from a curated database of 100+ clinically significant pairs
- 📜 **Beers Criteria Alerts** — AGS 2023 potentially inappropriate medications for elderly
- 🔄 **STOPP/START Recommendations** — European deprescribing/prescribing criteria (v3, 2023)
- 🧬 **AI-Predicted Interactions** — TxGemma predicts novel DDIs from molecular structure
- 📄 **AI Risk Reports** — Gemma 4 generates clinical summaries and patient-friendly explanations

## 🧠 Three Gemma Models

| Model | Role | Deployment |
|-------|------|------------|
| **MedGemma 4B-IT** | Parse free-text prescriptions → structured medication lists | AMD GPU pod (vLLM + ROCm) |
| **TxGemma 2B** | Predict drug-drug interactions from SMILES molecular structures | AMD GPU pod (vLLM + ROCm) |
| **Gemma 4 31B** | Generate clinical risk reports and deprescribing suggestions | Fireworks AI API |

## 🏗️ Architecture

```
┌──────────────────────────────────┐
│      Streamlit Web UI            │
│  (Input → Dashboard → Reports)   │
├──────────────────────────────────┤
│      Analysis Pipeline           │
│  Parse → Check → Predict → Report│
├───────┬────────┬────────┬────────┤
│DDInter│ Beers  │ STOPP/ │ Gemma  │
│DB +   │Criteria│ START  │ Models │
│RxNorm │ JSON   │ JSON   │ (3x)   │
└───────┴────────┴────────┴────────┘
```

## 🚀 Quick Start

### Option 1: Local Python (Fastest)

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/druglens.git
cd druglens

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your Fireworks AI API key

# Run
streamlit run app.py
```

Open http://localhost:8501

### Option 2: Docker (CPU-only, Fireworks API)

```bash
cp .env.example .env
# Add your FIREWORKS_API_KEY to .env

docker compose --profile cpu-only up --build
```

### Option 3: Docker with AMD GPU (Full Pipeline)

```bash
cp .env.example .env
# Add FIREWORKS_API_KEY and HF_TOKEN to .env

docker compose --profile gpu up --build
```

Requires: AMD GPU with ROCm drivers installed.

## 📋 Usage

1. **Enter medications** — free text or one per line (brand or generic names accepted)
2. **Set patient info** — age, conditions, eGFR
3. **Click Analyze** — get instant results across 5 tabs
4. **Try demo cases** — 3 pre-loaded scenarios (mild, moderate, severe)

### Demo Cases

| Case | Patient | Medications | Expected Risk |
|------|---------|-------------|---------------|
| Mild | 70yo, HTN + DM2 | metformin, lisinopril, amlodipine | LOW |
| Moderate | 78yo, OA + GERD + HTN + depression | omeprazole, ibuprofen, lisinopril, sertraline | MODERATE |
| Severe | 85yo, AFib + anxiety + insomnia + pain + CHF | warfarin, digoxin, amiodarone, lorazepam, oxycodone, diphenhydramine, furosemide, KCl | HIGH |

## 🔧 Configuration

All settings via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `FIREWORKS_API_KEY` | — | Required for Gemma 4 reports |
| `FIREWORKS_BASE_URL` | `https://api.fireworks.ai/inference/v1` | Fireworks API endpoint |
| `GEMMA_MODEL` | `accounts/fireworks/models/gemma-4-31b-it` | Gemma model on Fireworks |
| `MEDGEMMA_BASE_URL` | `http://localhost:8001/v1` | Local MedGemma endpoint |
| `TXGEMMA_BASE_URL` | `http://localhost:8002/v1` | Local TxGemma endpoint |
| `USE_LLM_PARSER` | `true` | Enable MedGemma parsing |
| `USE_TXGEMMA` | `true` | Enable TxGemma predictions |
| `USE_GEMMA4` | `true` | Enable Gemma 4 reports |

## 📁 Project Structure

```
druglens/
├── app.py                  # Streamlit web UI
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container definition
├── docker-compose.yml      # Multi-service orchestration
├── .env.example            # Environment template
├── data/
│   ├── beers_criteria.json     # AGS Beers 2023 (50+ PIMs)
│   ├── stopp_start.json        # STOPP/START v3 2023 (40+20 rules)
│   └── drug_interactions.json  # 100+ clinically significant DDIs
└── src/
    ├── config.py               # Configuration
    ├── drug_interactions.py     # DDI checking + Beers + STOPP/START
    ├── med_parser.py            # MedGemma + regex parser
    ├── ddi_predictor.py         # TxGemma DDI prediction
    ├── report_generator.py      # Gemma 4 report generation
    └── analyzer.py              # Main orchestrator
```

## 🏆 AMD Platform Usage

- **AMD Developer Cloud** — MedGemma 4B and TxGemma 2B served via vLLM on AMD Instinct GPUs
- **ROCm** — GPU computing platform for model inference
- **Fireworks AI** — Gemma 4 31B inference on AMD-hosted infrastructure

## ⚠️ Disclaimer

DrugLens is for **educational and research purposes only**. It is not a substitute for professional medical advice, diagnosis, or treatment. Always consult a qualified healthcare provider before making medication changes.

## 📄 License

MIT

## 🙏 Credits

- **AGS Beers Criteria** — American Geriatrics Society
- **STOPP/START v3** — O'Mahony et al. (2023), CC BY 4.0
- **Google DeepMind** — MedGemma, TxGemma, Gemma 4
- **AMD** — Developer Cloud, ROCm
- **Fireworks AI** — Model inference API
