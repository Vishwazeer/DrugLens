# 💊 DrugLens — AI-Powered Geriatric Polypharmacy Risk Analyzer

> **AMD Developer Hackathon: ACT II — Track 3 (Unicorn Track)**  
> An advanced clinical decision support tool designed to identify medication risks, drug-drug interactions, Beers Criteria violations, and STOPP/START mismatches in elderly patients using a multi-model Gemma pipeline.

---

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Streamlit-1.45-FF4B4B?style=for-the-badge&logo=streamlit" alt="Streamlit">
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

**DrugLens** provides clinicians with an instant, structured audit of complex geriatric medication regimens, matching them against gold-standard clinical rulesets while leveraging local and remote Gemma models to parse text, predict structural interactions, and write clinical safety reports.

---

## 🏗️ Multi-Model Gemma Architecture

To maximize performance, privacy, and eligibility for the best AMD-hosted Gemma prize, DrugLens orchestrates **three distinct Gemma models**:

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
│   [Model 2] TxGemma 2B    │                   │   [Model 3] Gemma 4 31B   │
│  Predicts novel DDIs from │                   │ Generates final clinical  │
│  molecular SMILES strings │                   │ report & patient summary  │
└───────────────────────────┘                   └───────────────────────────┘
 ◄── (Local AMD GPU / vLLM)                      ◄── (Fireworks AI / AMD)
```

1. **MedGemma 4B-IT (Local on AMD Instinct GPU / vLLM + ROCm)**
   * **Role**: Clinical parsing. Extracts medication names, dosages, route, and frequency from raw, unstructured clinical entry notes.
2. **TxGemma 2B (Local on AMD Instinct GPU / vLLM + ROCm)**
   * **Role**: Therapeutic interaction prediction. For drug pairs not present in our verified database, TxGemma resolves their molecular SMILES structures via PubChem and predicts potential structural interactions.
3. **Gemma 4 31B-IT (Remote API via Fireworks AI on AMD Infrastructure)**
   * **Role**: Report orchestration and synthesis. Reviews the compiled list of interactions, Beers alerts, and STOPP/START flags to generate a professional clinical safety report and a simplified patient-friendly summary.

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
| **Risk Report** | **Gemma 4 31B** (Fireworks) writes custom clinical analysis | **Rule-Based Engine** compiles score & fills structured template |

---

## 🚀 Step-by-Step Walkthrough

### 1. Local Python Run (CPU-Only / API Mode)

Perfect for rapid testing. This mode runs the Streamlit UI and local rules engine, utilizing the Fireworks API for Gemma 4 reports.

```bash
# Clone the repository
git clone https://github.com/Vishwazeer/DrugLens.git
cd DrugLens

# Install requirements
pip install -r requirements.txt

# Create .env config
cp .env.example .env
# Edit .env and insert your: FIREWORKS_API_KEY=your_key_here

# Launch the app
streamlit run app.py
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
*Port exposed: `8501`*

### Full GPU Mode (MedGemma + TxGemma + App served locally on ROCm)
```bash
docker compose --profile gpu up --build
```
*Note: Requires AMD GPU pass-through capability inside Docker.*

---

## 🧪 Interactive Demo Cases

To help judges evaluate the application immediately, the sidebar contains three pre-loaded clinical scenarios:

* **Case 1 — Mild (Low Risk)**: A 70yo patient on metformin, lisinopril, and amlodipine. Demonstrates how the system handles safe, standard therapies without triggering false alarms.
* **Case 2 — Moderate (Medium Risk)**: A 78yo patient on ibuprofen, lisinopril, sertraline, and omeprazole. Triggers:
  * NSAID + ACE inhibitor interaction (acute kidney injury risk).
  * Beers warning for long-term PPI use (osteoporosis/infection risk).
* **Case 3 — Severe (High Risk)**: An 85yo patient on 8 medications (warfarin, digoxin, amiodarone, lorazepam, oxycodone, diphenhydramine, furosemide, KCl). Triggers:
  * Major interactions: Warfarin ↔ Amiodarone, Digoxin ↔ Amiodarone.
  * FDA Black Box: Opioid (oxycodone) + Benzodiazepine (lorazepam) respiratory depression.
  * Beers: Benzodiazepines, high-dose digoxin, and first-generation antihistamines in the elderly.
  * High anticholinergic burden.

---

## 📁 Repository Structure

```
DrugLens/
├── app.py                  # Streamlit Web UI & visualization dashboards
├── setup_amd_pod.sh        # Automates ROCm + vLLM model deployments
├── Dockerfile              # Docker image definition for Streamlit App
├── docker-compose.yml      # Multi-service container definitions
├── requirements.txt        # Python package dependencies
├── data/
│   ├── beers_criteria.json     # Digitized AGS Beers 2023 PIMs
│   ├── stopp_start.json        # Digitized STOPP/START v3 rules
│   └── drug_interactions.json  # Curated index of 100+ clinical DDIs
└── src/
    ├── config.py               # Config parsing
    ├── drug_interactions.py     # Deterministic rules matching engine
    ├── med_parser.py            # Parser orchestrator
    ├── ddi_predictor.py         # TxGemma SMILES-based predictor
    ├── report_generator.py      # Gemma 4 summary compiler
    └── analyzer.py              # Main orchestrator pipeline
```

---

## ⚠️ Disclaimer

DrugLens is for **educational, demonstration, and research purposes only**. It is not a certified diagnostic tool or a substitute for professional clinical judgment. Always consult a licensed medical professional before making adjustments to any medication regimen.
