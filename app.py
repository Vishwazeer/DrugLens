import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Imports must follow load_dotenv() so src.config resolves the populated env
from src import config  # noqa: E402
from src.analyzer import CONDITION_OPTIONS, analyze_medications, get_demo_cases  # noqa: E402
from src.drug_interactions import normalize_drug_name  # noqa: E402

# --- Page Config ---
st.set_page_config(
    page_title="DrugLens — Polypharmacy Risk Analyzer",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Design system — "clinical instrument panel"
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Instrument+Serif:ital@0;1&family=Spline+Sans+Mono:wght@400;500;600;700&display=swap');

:root {
    --bg: #0A0D13;
    --surface: #11161F;
    --surface-2: #171D29;
    --line: rgba(154, 168, 196, 0.14);
    --line-strong: rgba(154, 168, 196, 0.28);
    --ink: #E9ECF4;
    --ink-2: #A8B1C5;
    --ink-3: #6C7691;
    --brand: #E8434A;
    --brand-soft: rgba(232, 67, 74, 0.10);
    --sev-high: #E14953;
    --sev-high-soft: rgba(225, 73, 83, 0.09);
    --sev-mod: #D98E3B;
    --sev-mod-soft: rgba(217, 142, 59, 0.09);
    --sev-low: #3FAE7E;
    --sev-low-soft: rgba(63, 174, 126, 0.09);
    --sev-info: #5B8DEF;
    --sev-info-soft: rgba(91, 141, 239, 0.09);
    --mono: 'Spline Sans Mono', ui-monospace, monospace;
    --sans: 'Instrument Sans', sans-serif;
    --serif: 'Instrument Serif', serif;
}

/* ---- Global chrome ---- */
html, body, .stApp { font-family: var(--sans); }
.stApp {
    background:
        radial-gradient(1100px 500px at 8% -10%, rgba(232,67,74,0.055), transparent 60%),
        radial-gradient(900px 480px at 100% 0%, rgba(91,141,239,0.05), transparent 55%),
        var(--bg);
}
.stApp::before {
    content: "";
    position: fixed; inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)' opacity='0.028'/%3E%3C/svg%3E");
    pointer-events: none; z-index: 0;
}
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 1.4rem; max-width: 1240px; }

h3 { font-weight: 600; letter-spacing: -0.01em; }

/* ---- Sidebar ---- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0C1018 0%, #0A0D13 100%);
    border-right: 1px solid var(--line);
}
section[data-testid="stSidebar"] .block-container { padding-top: 1.6rem; }

.side-label {
    font-family: var(--mono);
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--ink-3);
    display: flex; align-items: center; gap: 0.6rem;
    margin: 0.4rem 0 0.5rem 0;
}
.side-label::after { content: ""; flex: 1; height: 1px; background: var(--line); }

/* ---- Native widget polish ---- */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 4px;
    width: fit-content;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 4px 14px;
    color: var(--ink-2);
    font-weight: 500;
}
.stTabs [aria-selected="true"] {
    background: var(--surface-2) !important;
    color: var(--ink) !important;
    box-shadow: inset 0 0 0 1px var(--line-strong);
}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }

[data-testid="stBaseButton-primary"] {
    background: linear-gradient(180deg, #F0565C, #D93840);
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 10px;
    font-weight: 600;
    letter-spacing: 0.02em;
    box-shadow: 0 8px 22px -10px rgba(232,67,74,0.55);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
[data-testid="stBaseButton-primary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 12px 26px -10px rgba(232,67,74,0.7);
}

[data-testid="stTextArea"] textarea {
    background: var(--surface);
    border: 1px solid var(--line);
    font-family: var(--mono);
    font-size: 0.86rem;
    line-height: 1.7;
}
[data-testid="stNumberInput"] input { font-family: var(--mono); }

[data-testid="stAlert"] {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 10px;
}

/* ---- Header ---- */
.dl-hero {
    position: relative;
    background: linear-gradient(135deg, #10141D 0%, #131926 55%, #10141D 100%);
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 1.9rem 2.2rem 2.1rem 2.2rem;
    margin-bottom: 1.4rem;
    overflow: hidden;
}
.dl-hero::after {
    content: "";
    position: absolute; inset: 0;
    background: radial-gradient(600px 220px at 12% 0%, rgba(232,67,74,0.10), transparent 65%);
    pointer-events: none;
}
.dl-hero-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 1.5rem; flex-wrap: wrap; }
.dl-wordmark {
    font-size: 2.7rem;
    font-weight: 700;
    letter-spacing: -0.035em;
    color: var(--ink);
    line-height: 1;
    margin: 0;
}
.dl-wordmark .accent { color: var(--brand); }
.dl-tagline {
    font-family: var(--serif);
    font-style: italic;
    font-size: 1.18rem;
    color: var(--ink-2);
    margin: 0.55rem 0 0 0.1rem;
}
.dl-chips { display: flex; gap: 0.45rem; flex-wrap: wrap; justify-content: flex-end; max-width: 380px; }
.dl-chip {
    font-family: var(--mono);
    font-size: 0.67rem;
    font-weight: 500;
    letter-spacing: 0.04em;
    color: var(--ink-2);
    background: rgba(255,255,255,0.03);
    border: 1px solid var(--line);
    padding: 0.3rem 0.65rem;
    border-radius: 999px;
    white-space: nowrap;
}
.dl-chip b { color: var(--ink); font-weight: 600; }
.dl-chip.red { border-color: rgba(232,67,74,0.4); color: #F3979B; }

.dl-ecg { margin-top: 1.3rem; height: 34px; position: relative; }
.dl-ecg svg { width: 100%; height: 100%; display: block; }
.dl-ecg path {
    fill: none;
    stroke: var(--brand);
    stroke-width: 1.6;
    opacity: 0.85;
    stroke-dasharray: 1200;
    stroke-dashoffset: 1200;
    animation: dl-trace 3.2s ease-out forwards;
    filter: drop-shadow(0 0 6px rgba(232,67,74,0.45));
}
@keyframes dl-trace { to { stroke-dashoffset: 0; } }

/* ---- Cards & tiles ---- */
@keyframes dl-rise { from { opacity: 0; transform: translateY(9px); } to { opacity: 1; transform: none; } }

.tile {
    position: relative;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 1.15rem 1.3rem 1.2rem 1.3rem;
    animation: dl-rise 0.45s ease-out backwards;
    transition: border-color 0.2s ease, transform 0.2s ease;
    min-height: 118px;
}
.tile:hover { border-color: var(--line-strong); transform: translateY(-2px); }
.tile::before, .tile::after {
    content: ""; position: absolute; width: 9px; height: 9px; opacity: 0.55;
}
.tile::before { top: 7px; left: 7px; border-top: 1px solid var(--ink-3); border-left: 1px solid var(--ink-3); }
.tile::after { bottom: 7px; right: 7px; border-bottom: 1px solid var(--ink-3); border-right: 1px solid var(--ink-3); }

.tile-label {
    font-family: var(--mono);
    font-size: 0.66rem;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin-bottom: 0.45rem;
}
.tile-value {
    font-family: var(--mono);
    font-size: 2.15rem;
    font-weight: 600;
    line-height: 1;
    color: var(--ink);
}
.tile-sub { font-size: 0.74rem; color: var(--ink-3); margin-top: 0.45rem; }

.risk-word { font-family: var(--sans); font-size: 2rem; font-weight: 700; letter-spacing: -0.01em; line-height: 1.1; }
.risk-dot {
    display: inline-block; width: 9px; height: 9px; border-radius: 50%;
    margin-right: 0.55rem; vertical-align: 3px;
}
.risk-dot.pulse { animation: dl-pulse 1.6s ease-out infinite; }
@keyframes dl-pulse {
    0% { box-shadow: 0 0 0 0 rgba(225,73,83,0.45); }
    100% { box-shadow: 0 0 0 11px rgba(225,73,83,0); }
}
.risk-track { position: relative; height: 4px; background: rgba(255,255,255,0.06); border-radius: 2px; margin-top: 0.85rem; }
.risk-fill { position: absolute; inset: 0 auto 0 0; border-radius: 2px; }
.risk-tick { position: absolute; top: -3px; width: 1px; height: 10px; background: var(--ink-3); }
.risk-tick span {
    position: absolute; top: 11px; left: -8px;
    font-family: var(--mono); font-size: 0.56rem; letter-spacing: 0.08em; color: var(--ink-3);
}

/* ---- Section headers & alert cards ---- */
.sec {
    display: flex; align-items: center; gap: 0.7rem;
    font-family: var(--mono);
    font-size: 0.7rem; font-weight: 600;
    letter-spacing: 0.16em; text-transform: uppercase;
    color: var(--ink-2);
    margin: 1.3rem 0 0.8rem 0;
}
.sec .count { color: var(--brand); }
.sec::after { content: ""; flex: 1; height: 1px; background: var(--line); }

.acard {
    position: relative;
    background: var(--surface);
    border: 1px solid var(--line);
    border-left: none;
    border-radius: 12px;
    padding: 0.95rem 1.15rem 0.95rem 1.35rem;
    margin-bottom: 0.65rem;
    overflow: hidden;
    animation: dl-rise 0.4s ease-out backwards;
    transition: border-color 0.2s ease, transform 0.2s ease;
}
.acard:hover { border-color: var(--line-strong); transform: translateX(2px); }
.acard::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; }
.acard.high::before { background: var(--sev-high); }
.acard.moderate::before { background: var(--sev-mod); }
.acard.low::before { background: var(--sev-low); }
.acard.info::before { background: var(--sev-info); }
.acard.high { background: linear-gradient(90deg, var(--sev-high-soft), var(--surface) 40%); }
.acard.moderate { background: linear-gradient(90deg, var(--sev-mod-soft), var(--surface) 40%); }
.acard.low { background: linear-gradient(90deg, var(--sev-low-soft), var(--surface) 40%); }
.acard.info { background: linear-gradient(90deg, var(--sev-info-soft), var(--surface) 40%); }
.acard:nth-of-type(1) { animation-delay: 0.02s; } .acard:nth-of-type(2) { animation-delay: 0.06s; }
.acard:nth-of-type(3) { animation-delay: 0.10s; } .acard:nth-of-type(4) { animation-delay: 0.14s; }
.acard:nth-of-type(5) { animation-delay: 0.18s; } .acard:nth-of-type(6) { animation-delay: 0.22s; }

.acard-head { display: flex; align-items: baseline; gap: 0.6rem; flex-wrap: wrap; margin-bottom: 0.45rem; }
.acard-id {
    font-family: var(--mono); font-size: 0.63rem; font-weight: 600;
    letter-spacing: 0.06em; color: var(--ink-3);
    border: 1px solid var(--line); border-radius: 5px; padding: 0.1rem 0.4rem;
}
.acard-title { font-size: 0.95rem; font-weight: 600; color: var(--ink); }
.acard-sev {
    font-family: var(--mono); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.14em;
    margin-left: auto;
}
.acard-sev.high { color: var(--sev-high); } .acard-sev.moderate { color: var(--sev-mod); }
.acard-sev.low { color: var(--sev-low); } .acard-sev.info { color: var(--sev-info); }
.acard-body { font-size: 0.83rem; color: var(--ink-2); line-height: 1.55; }
.acard-body b { color: var(--ink); font-weight: 600; }

.empty-note {
    display: flex; align-items: center; gap: 0.7rem;
    background: var(--surface); border: 1px dashed var(--line-strong);
    border-radius: 12px; padding: 1rem 1.2rem;
    color: var(--ink-2); font-size: 0.88rem;
}
.empty-note .ok { color: var(--sev-low); font-weight: 700; }

/* ---- Footer ---- */
.dl-footer {
    border-top: 1px solid var(--line);
    margin-top: 2.6rem; padding: 1.3rem 0 0.6rem 0;
    text-align: center;
    font-family: var(--mono); font-size: 0.68rem; letter-spacing: 0.05em;
    color: var(--ink-3); line-height: 2;
}

@media (prefers-reduced-motion: reduce) {
    .tile, .acard, .dl-ecg path { animation: none !important; }
}
</style>
""", unsafe_allow_html=True)


# --- Header ---
# The 3rd (cloud) model is configurable; show whatever Fireworks model is set.
_report_label = config.REPORT_MODEL.split("/")[-1]
st.markdown(f"""
<div class="dl-hero">
    <div class="dl-hero-top">
        <div>
            <h1 class="dl-wordmark">Drug<span class="accent">Lens</span></h1>
            <p class="dl-tagline">a second pair of eyes for every prescription</p>
        </div>
        <div class="dl-chips">
            <span class="dl-chip"><b>MedGemma 4B</b>&nbsp;· parse</span>
            <span class="dl-chip"><b>TxGemma 2B</b>&nbsp;· predict</span>
            <span class="dl-chip"><b>{_report_label}</b>&nbsp;· report</span>
            <span class="dl-chip red">AMD Instinct · ROCm</span>
            <span class="dl-chip red">Fireworks AI</span>
        </div>
    </div>
    <div class="dl-ecg">
        <svg viewBox="0 0 1000 34" preserveAspectRatio="none">
            <path d="M0,20 L110,20 L122,20 L130,10 L138,28 L146,20 L260,20 L272,20 L282,4 L292,32 L300,20
                     L430,20 L442,20 L450,12 L458,26 L466,20 L600,20 L615,20 L625,2 L637,33 L646,20
                     L780,20 L792,20 L800,11 L808,27 L816,20 L1000,20"/>
        </svg>
    </div>
</div>
""", unsafe_allow_html=True)


# --- Sidebar ---
with st.sidebar:
    st.markdown('<div class="side-label">Pipeline</div>', unsafe_allow_html=True)

    use_llm = st.toggle("MedGemma parser", value=config.USE_LLM_PARSER,
                        help="Parse medications with MedGemma AI. Disable for regex-only parsing.")
    use_txgemma = st.toggle("TxGemma predictions", value=config.USE_TXGEMMA,
                            help="Predict unknown drug interactions with TxGemma.")
    use_gemma4 = st.toggle("Cloud AI reports", value=config.USE_GEMMA4,
                           help="Generate the narrative safety report with the cloud model on Fireworks AI.")

    st.markdown('<div class="side-label" style="margin-top:1.4rem;">Demo cases</div>',
                unsafe_allow_html=True)

    demo_cases = get_demo_cases()
    selected_demo = st.selectbox(
        "Load a demo case",
        options=["— Select —"] + [c["name"] for c in demo_cases],
        index=0,
        label_visibility="collapsed",
    )

    if selected_demo != "— Select —":
        case = next(c for c in demo_cases if c["name"] == selected_demo)
        st.info(case["description"])

    st.markdown('<div class="side-label" style="margin-top:1.4rem;">Method</div>',
                unsafe_allow_html=True)
    st.markdown("""
    1. **Parse** — extract medications from text
    2. **Check** — interactions · Beers · STOPP/START
    3. **Predict** — novel DDIs from SMILES
    4. **Report** — risk synthesis & deprescribing
    """)

    st.markdown("""
    <div style="margin-top:1.6rem; display:flex; gap:0.4rem; flex-wrap:wrap;">
        <span class="dl-chip red">AMD Hackathon · ACT II</span>
        <span class="dl-chip">Track 3 — Unicorn</span>
    </div>
    """, unsafe_allow_html=True)


# --- Main Input Section ---
col_input, col_patient = st.columns([3, 2])

with col_input:
    st.markdown("### 📋 Medication Input")

    # Pre-fill from demo case if selected
    default_meds = ""
    if selected_demo != "— Select —":
        case = next(c for c in demo_cases if c["name"] == selected_demo)
        default_meds = case["medication_text"]

    medication_text = st.text_area(
        "Enter medications (free text or one per line)",
        value=default_meds,
        height=180,
        placeholder="Example:\nmetformin 500mg twice daily\nlisinopril 10mg once daily\namlodipine 5mg daily\nomeprazole 20mg daily"
    )

with col_patient:
    st.markdown("### 👤 Patient Information")

    default_age = 75
    default_conditions = []
    if selected_demo != "— Select —":
        case = next(c for c in demo_cases if c["name"] == selected_demo)
        default_age = case["patient_age"]
        default_conditions = case.get("conditions", [])

    patient_age = st.number_input("Age", min_value=18, max_value=120, value=default_age)

    patient_conditions = st.multiselect(
        "Conditions",
        options=CONDITION_OPTIONS,
        default=default_conditions
    )

    patient_egfr = st.number_input(
        "eGFR (mL/min/1.73m²)",
        min_value=5, max_value=150, value=60,
        help="Estimated glomerular filtration rate. Normal: >90, Mild: 60-89, Moderate: 30-59, Severe: <30"
    )


# --- Analyze Button ---
analyze_clicked = st.button("🔍 Analyze Medications", type="primary", use_container_width=True)

if analyze_clicked and medication_text.strip():
    with st.spinner("Analyzing medications..."):
        results = analyze_medications(
            medication_text=medication_text,
            patient_age=patient_age,
            patient_conditions=patient_conditions,
            patient_egfr=float(patient_egfr),
            use_llm_parser=use_llm,
            use_txgemma=use_txgemma,
            use_gemma4=use_gemma4
        )

    # Store results in session state
    st.session_state["results"] = results
    st.session_state["medication_text"] = medication_text

elif analyze_clicked:
    st.warning("Enter medications first.")


SEVERITY_CLASS = {
    "major": "high", "high": "high",
    "moderate": "moderate",
    "minor": "low", "low": "low",
}

RISK_STYLE = {
    "HIGH": ("var(--sev-high)", True),
    "MODERATE": ("var(--sev-mod)", False),
    "LOW": ("var(--sev-low)", False),
    "MINIMAL": ("var(--sev-low)", False),
}


def alert_card(css: str, id_chip: str, title: str, sev_label: str, body_html: str) -> str:
    sev_html = (
        f'<span class="acard-sev {css}">{sev_label}</span>' if sev_label else ""
    )
    id_html = f'<span class="acard-id">{id_chip}</span>' if id_chip else ""
    return f"""
    <div class="acard {css}">
        <div class="acard-head">{id_html}<span class="acard-title">{title}</span>{sev_html}</div>
        <div class="acard-body">{body_html}</div>
    </div>
    """


# --- Results Display ---
if "results" in st.session_state:
    results = st.session_state["results"]

    # --- Risk Overview ---
    risk_level = results.get("risk_level", "UNKNOWN")
    risk_score = results.get("risk_score", 0)
    risk_color, risk_pulse = RISK_STYLE.get(risk_level, ("var(--ink-2)", False))

    n_meds = len(results.get("parsed_medications", []))
    n_interactions = len(results.get("interactions", []))
    n_alerts = (len(results.get("beers_alerts", []))
                + len(results.get("stopp_start", {}).get("stopp", [])))

    track_pct = min(risk_score / 16 * 100, 100)
    pulse_cls = "pulse" if risk_pulse else ""

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class="tile" style="animation-delay:0.02s;">
            <div class="tile-label">Overall risk</div>
            <div class="risk-word" style="color:{risk_color};">
                <span class="risk-dot {pulse_cls}" style="background:{risk_color};"></span>{risk_level}
            </div>
            <div class="risk-track">
                <div class="risk-fill" style="width:{track_pct}%; background:{risk_color};"></div>
                <div class="risk-tick" style="left:31.25%;"><span>MOD</span></div>
                <div class="risk-tick" style="left:75%;"><span>HIGH</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="tile" style="animation-delay:0.07s;">
            <div class="tile-label">Medications</div>
            <div class="tile-value">{n_meds}</div>
            <div class="tile-sub">parsed from input</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        ix_color = "var(--sev-high)" if n_interactions else "var(--sev-low)"
        st.markdown(f"""
        <div class="tile" style="animation-delay:0.12s;">
            <div class="tile-label">Interactions</div>
            <div class="tile-value" style="color:{ix_color};">{n_interactions}</div>
            <div class="tile-sub">database-confirmed pairs</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        al_color = "var(--sev-mod)" if n_alerts else "var(--sev-low)"
        st.markdown(f"""
        <div class="tile" style="animation-delay:0.17s;">
            <div class="tile-label">Criteria alerts</div>
            <div class="tile-value" style="color:{al_color};">{n_alerts}</div>
            <div class="tile-sub">Beers + STOPP flags</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("")

    # --- Tabs for detailed results ---
    tab_interactions, tab_beers, tab_stopp, tab_report, tab_raw = st.tabs([
        "⚠️ Drug Interactions", "📜 Beers Criteria", "🔄 STOPP/START", "📄 AI Report", "🔧 Raw Data"
    ])

    # --- Drug Interactions Tab ---
    with tab_interactions:
        interactions = results.get("interactions", [])
        predicted = results.get("predicted_interactions", [])

        if interactions:
            st.markdown(
                f'<div class="sec">Database-confirmed interactions'
                f'<span class="count">{len(interactions)}</span></div>',
                unsafe_allow_html=True,
            )
            for ix in interactions:
                sev = ix.get("severity", "moderate")
                css = SEVERITY_CLASS.get(sev, "moderate")
                evidence = ix.get("evidence_level", "")
                evidence_line = (
                    f"<br><b>Evidence:</b> {evidence.capitalize()}" if evidence else ""
                )
                body = (
                    f"<b>Effect:</b> {ix.get('effect', 'Unknown')}<br>"
                    f"<b>Mechanism:</b> {ix.get('mechanism', 'Unknown')}<br>"
                    f"<b>Management:</b> {ix.get('management', 'Consult prescriber')}"
                    f"{evidence_line}"
                )
                st.markdown(
                    alert_card(
                        css, "DDI",
                        f"{ix.get('drug_a', '?')} ↔ {ix.get('drug_b', '?')}",
                        sev.upper(), body,
                    ),
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div class="empty-note"><span class="ok">●</span>'
                "No known drug interactions found in the database.</div>",
                unsafe_allow_html=True,
            )

        if predicted:
            st.markdown(
                f'<div class="sec">TxGemma predicted interactions'
                f'<span class="count">{len(predicted)}</span></div>',
                unsafe_allow_html=True,
            )
            for px_item in predicted:
                body = (
                    f"{px_item.get('predicted_interaction', 'Potential interaction predicted')}<br>"
                    f"<b>Confidence:</b> {px_item.get('confidence', 'N/A')}"
                )
                st.markdown(
                    alert_card(
                        "info", "AI",
                        f"{px_item.get('drug_a', '?')} ↔ {px_item.get('drug_b', '?')}",
                        "PREDICTED", body,
                    ),
                    unsafe_allow_html=True,
                )

        # Interaction heatmap
        if interactions and len(results.get("parsed_medications", [])) >= 2:
            st.markdown('<div class="sec">Interaction matrix</div>', unsafe_allow_html=True)
            meds = [m.get("name", m) if isinstance(m, dict) else str(m)
                    for m in results["parsed_medications"]]
            n = len(meds)
            matrix = [[0] * n for _ in range(n)]

            for ix in interactions:
                da = normalize_drug_name(ix.get("drug_a", ""))
                db = normalize_drug_name(ix.get("drug_b", ""))
                for i, m in enumerate(meds):
                    for j, m2 in enumerate(meds):
                        nm1 = normalize_drug_name(m)
                        nm2 = normalize_drug_name(m2)
                        if (nm1 == da and nm2 == db) or (nm1 == db and nm2 == da):
                            sev_score = {"major": 3, "moderate": 2, "minor": 1}.get(
                                ix.get("severity", "moderate"), 2)
                            matrix[i][j] = sev_score
                            matrix[j][i] = sev_score

            sev_names = [["None", "Minor", "Moderate", "Major"][v] for row in matrix for v in row]
            sev_names = [sev_names[i * n:(i + 1) * n] for i in range(n)]

            fig = go.Figure(data=go.Heatmap(
                z=matrix,
                x=meds,
                y=meds,
                customdata=sev_names,
                hovertemplate="%{y} ↔ %{x}<br>Severity: %{customdata}<extra></extra>",
                xgap=3,
                ygap=3,
                zmin=0,
                zmax=3,
                colorscale=[
                    [0.0, "#171D29"], [0.2499, "#171D29"],
                    [0.25, "#EDCB6B"], [0.4999, "#EDCB6B"],
                    [0.5, "#CE6C28"], [0.7499, "#CE6C28"],
                    [0.75, "#E14953"], [1.0, "#E14953"],
                ],
                showscale=True,
                colorbar=dict(
                    tickvals=[0.375, 1.125, 1.875, 2.625],
                    ticktext=["None", "Minor", "Moderate", "Major"],
                    thickness=10,
                    len=0.62,
                    outlinewidth=0,
                    tickfont=dict(family="Spline Sans Mono", size=11, color="#A8B1C5"),
                ),
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                height=420,
                margin=dict(l=10, r=10, t=10, b=10),
                font=dict(family="Spline Sans Mono", size=12, color="#A8B1C5"),
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=False, autorange="reversed"),
            )
            st.plotly_chart(fig, use_container_width=True)

    # --- Beers Criteria Tab ---
    with tab_beers:
        beers = results.get("beers_alerts", [])
        if beers:
            st.markdown(
                f'<div class="sec">Beers criteria alerts'
                f'<span class="count">{len(beers)}</span></div>',
                unsafe_allow_html=True,
            )
            for alert in beers:
                sev = alert.get("severity", "moderate")
                css = SEVERITY_CLASS.get(sev, "moderate")
                exceptions = alert.get("exceptions", "")
                exceptions_line = f"<br><b>Exceptions:</b> {exceptions}" if exceptions else ""
                body = (
                    f"<b>Drugs matched:</b> {', '.join(alert.get('matched_drugs', []))}<br>"
                    f"<b>Rationale:</b> {alert.get('rationale', 'N/A')}<br>"
                    f"<b>Category:</b> {alert.get('category', 'N/A')}"
                    f"{exceptions_line}"
                )
                st.markdown(
                    alert_card(
                        css, alert.get("id", ""),
                        f"{alert.get('drug_class', 'Unknown')} — {alert.get('recommendation', 'Review')}",
                        sev.upper(), body,
                    ),
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div class="empty-note"><span class="ok">●</span>'
                "No Beers Criteria alerts triggered.</div>",
                unsafe_allow_html=True,
            )

    # --- STOPP/START Tab ---
    with tab_stopp:
        stopp = results.get("stopp_start", {}).get("stopp", [])
        start = results.get("stopp_start", {}).get("start", [])

        if stopp:
            st.markdown(
                f'<div class="sec">STOPP — consider stopping'
                f'<span class="count">{len(stopp)}</span></div>',
                unsafe_allow_html=True,
            )
            for rule in stopp:
                sev = rule.get("severity", "moderate")
                css = SEVERITY_CLASS.get(sev, "moderate")
                body = (
                    f"<b>Criteria:</b> {rule.get('criteria', '')}<br>"
                    f"<b>Drugs matched:</b> {', '.join(rule.get('matched_drugs', []))}<br>"
                    f"<b>Rationale:</b> {rule.get('rationale', '')}"
                )
                st.markdown(
                    alert_card(css, rule.get("id", ""), rule.get("category", ""),
                               sev.upper(), body),
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div class="empty-note"><span class="ok">●</span>'
                "No STOPP criteria triggered.</div>",
                unsafe_allow_html=True,
            )

        if start:
            st.markdown(
                f'<div class="sec">START — consider starting'
                f'<span class="count">{len(start)}</span></div>',
                unsafe_allow_html=True,
            )
            for rule in start:
                body = (
                    f"<b>Criteria:</b> {rule.get('criteria', '')}<br>"
                    f"<b>Suggested drugs:</b> {', '.join(rule.get('recommended_drugs', []))}<br>"
                    f"<b>Rationale:</b> {rule.get('rationale', '')}"
                )
                st.markdown(
                    alert_card("low", rule.get("id", ""), rule.get("category", ""),
                               "SUGGESTED", body),
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div class="empty-note"><span class="ok">●</span>'
                "No START suggestions applicable.</div>",
                unsafe_allow_html=True,
            )

    # --- AI Report Tab ---
    with tab_report:
        report = results.get("risk_report", {})
        if report:
            ai_score = report.get("risk_score_numeric")
            if ai_score is not None:
                st.markdown(f"#### 🤖 AI risk score: {ai_score}/100")
                st.caption(
                    "The cloud model's own 0–100 assessment — complements the rule-based "
                    "risk level shown in the overview card above."
                )

            if report.get("summary"):
                st.markdown("#### 📝 Summary")
                st.info(report["summary"])

            if report.get("clinical_summary"):
                st.markdown("#### 🏥 Clinical Summary")
                st.markdown(report["clinical_summary"])

            if report.get("deprescribing_suggestions"):
                st.markdown("#### 💊 Deprescribing Suggestions")
                for sug in report["deprescribing_suggestions"]:
                    body = (
                        f"<b>Reason:</b> {sug.get('reason', '')}<br>"
                        f"<b>Alternative:</b> {sug.get('alternative', 'Discuss with prescriber')}<br>"
                        f"<b>Priority:</b> {sug.get('priority', 'Medium')}"
                    )
                    st.markdown(
                        alert_card("moderate", "RX",
                                   f"Consider stopping: {sug.get('drug', '?')}", "", body),
                        unsafe_allow_html=True,
                    )

            if report.get("key_alerts"):
                st.markdown("#### 🚨 Key Alerts")
                for alert in report["key_alerts"]:
                    st.markdown(f"- {alert}")

            if report.get("recommendations"):
                st.markdown("#### ✅ Recommendations")
                for rec in report["recommendations"]:
                    st.markdown(f"- {rec}")
        else:
            st.info("Enable Cloud AI reports in settings for AI-powered reports, or run analysis first.")

        if results.get("patient_summary"):
            st.markdown("#### 👤 Patient-Friendly Summary")
            st.success(results["patient_summary"])

    # --- Raw Data Tab ---
    with tab_raw:
        st.markdown("#### Parsed Medications")
        if results.get("parsed_medications"):
            st.json(results["parsed_medications"])

        st.markdown("#### Full Analysis Results")
        # Remove large nested objects for display
        display_results = {k: v for k, v in results.items() if k != "risk_report"}
        st.json(display_results)

    # --- Errors ---
    if results.get("errors"):
        st.markdown("---")
        st.warning("⚠️ Some analysis steps encountered issues:")
        for err in results["errors"]:
            st.caption(f"• {err}")


# --- Footer ---
st.markdown("""
<div class="dl-footer">
    <p>DRUGLENS — AMD DEVELOPER HACKATHON: ACT II · TRACK 3 UNICORN</p>
    <p>FOR EDUCATIONAL AND RESEARCH PURPOSES ONLY · NOT A SUBSTITUTE FOR PROFESSIONAL MEDICAL ADVICE</p>
    <p>MEDGEMMA · TXGEMMA · CLOUD SYNTHESIS · AMD DEVELOPER CLOUD · FIREWORKS AI</p>
</div>
""", unsafe_allow_html=True)
