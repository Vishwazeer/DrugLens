# ⚠️ The Critical Challenge of Geriatric Polypharmacy

## 1. Introduction & Background
As global life expectancy increases, multi-morbidity (having two or more chronic health conditions) has become the norm rather than the exception in elderly care. Consequently, **polypharmacy**—defined as the daily use of five or more prescription medications—has risen to epidemic proportions. 

While multiple therapies are often necessary to manage chronic illnesses like diabetes, hypertension, and heart disease, the cumulative effect of these drugs in older adults introduces massive clinical and systemic risks.

---

## 2. The Core Problem
Geriatric patients process medications differently than younger adults. Aging bodies undergo significant changes in pharmacokinetics (how the body absorbs, distributes, metabolizes, and excretes drugs) and pharmacodynamics (how the drug affects the body):
* **Renal Decline**: Glomerular filtration rates (eGFR) naturally decrease with age, leading to dangerous accumulation of renally-cleared medications.
* **Hepatic Changes**: Reduced liver blood flow slows drug metabolism.
* **Blood-Brain Barrier permeability**: Increased sensitivity to central nervous system (CNS) active agents, raising the risk of delirium, confusion, and falls.

Standard clinical workflows often fail to audit these age-specific risk profiles, leading to **Adverse Drug Events (ADEs)**.

---

## 3. Quantifying the Impact

### Clinical Consequences
1. **Falls and Fractures**: Medications like benzodiazepines and first-generation antihistamines cause drowsiness and cognitive impairment, multiplying the risk of falls—the leading cause of injury-related death in seniors.
2. **Cognitive Decline**: Anticholinergic drugs (which block acetylcholine in the central and peripheral nervous systems) can mimic or accelerate dementia symptoms.
3. **Organ Failure**: Concomitant use of NSAIDs, ACE inhibitors, and diuretics ("the triple whammy") causes acute kidney injury (AKI).

### Socioeconomic Burden
* **Preventable Cost**: Adverse drug events in elderly care units generate **$3.5 billion in avoidable healthcare expenditures** annually in the United States alone.
* **Hospitalizations**: ADEs account for nearly **30% of all emergency hospital admissions** in adults aged 65 and older.
* **Mortality**: Iatrogenic drug complications are among the top ten leading causes of death in geriatric cohorts.

---

## 4. Why Current EHR Systems Fail

Existing Electronic Health Records (EHRs) and e-prescribing portals fall short due to three critical friction points:

### I. Alert Fatigue
Traditional systems rely on simple databases that flag *every* potential drug-drug interaction regardless of severity or clinical context. Doctors face hundreds of pop-ups per day, leading them to mute or ignore up to **90% of warnings**, potentially missing life-threatening alerts.

### II. Absence of Age-Specific Rules
Standard DDI checkers flag interactions between Drug A and Drug B. However, they do not check if **Drug A alone is inappropriate for an 85-year-old** (Beers Criteria), or if a patient's underlying conditions demand that a drug be stopped (STOPP) or started (START).

### III. Unstructured Clinical Notes
A significant portion of clinical documentation exists as free-text doctor's notes rather than neat, structured databases. Manually copying and pasting these notes into database checkers consumes valuable clinician time.

### IV. The "Novel Drug" Blindspot
Traditional checkers only know about pre-indexed interaction pairs. If a patient is prescribed a new or lesser-known drug combination, the system fails to predict a potential interaction.

---

## 5. The DrugLens Solution

DrugLens wraps a fast, digitized geriatric rules engine (Beers 2023, STOPP/START v3) in a two-tier architecture: **deterministic rules always run first**, and an LLM is invoked **only when the case warrants it**.

```
┌─────────────────────────────────┐
│        Free-Text Input          │  <-- Unstructured clinical notes
└────────────────┬────────────────┘
                 │
                 ▼  [Clinical Text Parser]
┌─────────────────────────────────┐
│     Structured Medication       │  <-- Extracts name, dose, frequency, route
│     + Patient Context           │      and age / eGFR / conditions from the note
└────────────────┬────────────────┘
                 │
                 ▼  [Deterministic Ruleset Engine — always runs, ~3 ms]
┌─────────────────────────────────┐
│  - 102 Curated DDIs Checked     │  <-- Combination-aware (AND-logic), not naive
│  - Beers Criteria Violations    │  <-- Age- and eGFR-gated
│  - STOPP/START Recommendations  │  <-- Conditions treated / therapies missing
└────────────────┬────────────────┘
                 │
                 ├──► LOW / MINIMAL risk ──► answered here. **0 LLM tokens spent.**
                 │
                 ▼  [Token-Efficient Router] — escalate only MODERATE / HIGH
┌─────────────────────────────────┐
│  Novel DDI Prediction           │  <-- Un-indexed pairs evaluated by the cloud
│  (un-indexed pairs + SMILES)    │      model, grounded in PubChem structures
└────────────────┬────────────────┘
                 │
                 ▼  [Cloud model via Fireworks AI]
┌─────────────────────────────────┐
│    Interactive Clinical Report  │  <-- Streaming narrative + deprescribing
│                                 │      suggestions + safer alternatives
└─────────────────────────────────┘
```

### How each failure mode is addressed

| EHR failure (§4) | How DrugLens answers it |
|---|---|
| **I. Alert fatigue** | Combination rules use **AND-semantics**: "opioid + benzodiazepine" fires only when *both* are present, never on one drug alone. Findings are severity-ranked and risk-scored. Our mild demo case produces **zero alerts** — the system stays quiet when nothing is wrong. |
| **II. No age-specific rules** | 61 AGS Beers 2023 rules + 38 STOPP + 20 START, gated on **age, comorbidities, and eGFR**. Drop eGFR to 25 and the renal rules activate live. |
| **III. Unstructured notes** | The parser reads free-text prescriptions *and* lifts patient age, eGFR, conditions and allergies straight out of the note. |
| **IV. Novel-drug blindspot** | Every drug pair with **no database entry** is sent to the cloud model, grounded in each drug's **PubChem SMILES structure**, to surface interactions no lookup table contains. |

By decoupling deterministic rule matching from predictive AI, DrugLens attacks alert fatigue at its root (precision, not volume) while still covering the novel-drug blindspot — and it spends **zero GPU tokens** on the low-risk majority of patients.

> **Scope note.** The public demo runs on a CPU-only host. The cloud model is served by Fireworks AI. A GPU path for MedGemma 4B / TxGemma 2B (vLLM + ROCm on AMD Instinct) is shipped and reviewable in this repo but is **not enabled in the public demo** — see *Honest Scope* in the README.
