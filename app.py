import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Imports must follow load_dotenv() so src.config resolves the populated env
from src.analyzer import analyze_medications, get_demo_cases  # noqa: E402
from src.drug_interactions import normalize_drug_name  # noqa: E402

# --- Page Config ---
st.set_page_config(
    page_title="DrugLens — Polypharmacy Risk Analyzer",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

/* Global */
.stApp {
    font-family: 'Inter', sans-serif;
}

/* Header */
.main-header {
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    padding: 2rem 2.5rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    border: 1px solid rgba(255,255,255,0.08);
}
.main-header h1 {
    color: #fff;
    font-size: 2.4rem;
    font-weight: 800;
    margin: 0;
    letter-spacing: -0.5px;
}
.main-header p {
    color: rgba(255,255,255,0.7);
    font-size: 1.05rem;
    margin: 0.3rem 0 0 0;
}
.badge-row {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.8rem;
    flex-wrap: wrap;
}
.badge {
    background: rgba(255,255,255,0.1);
    border: 1px solid rgba(255,255,255,0.15);
    color: #e0e0e0;
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 500;
    backdrop-filter: blur(8px);
}

/* Risk Cards */
.risk-card {
    padding: 1.5rem;
    border-radius: 14px;
    text-align: center;
    border: 1px solid rgba(255,255,255,0.06);
    transition: transform 0.2s ease;
}
.risk-card:hover {
    transform: translateY(-2px);
}
.risk-high {
    background: linear-gradient(135deg, #1a0000, #3d0000);
    border-color: rgba(239,68,68,0.3);
}
.risk-moderate {
    background: linear-gradient(135deg, #1a1200, #3d2e00);
    border-color: rgba(245,158,11,0.3);
}
.risk-low {
    background: linear-gradient(135deg, #001a00, #003d00);
    border-color: rgba(34,197,94,0.3);
}
.risk-minimal {
    background: linear-gradient(135deg, #001a1a, #003d3d);
    border-color: rgba(6,182,212,0.3);
}
.risk-score {
    font-size: 3rem;
    font-weight: 900;
    margin: 0;
}
.risk-label {
    font-size: 0.9rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 0.3rem;
}

/* Alert cards */
.alert-card {
    padding: 1rem 1.2rem;
    border-radius: 10px;
    margin-bottom: 0.6rem;
    border-left: 4px solid;
}
.alert-high {
    background: rgba(239,68,68,0.08);
    border-left-color: #ef4444;
}
.alert-moderate {
    background: rgba(245,158,11,0.08);
    border-left-color: #f59e0b;
}
.alert-low {
    background: rgba(34,197,94,0.08);
    border-left-color: #22c55e;
}
.alert-title {
    font-weight: 700;
    font-size: 0.95rem;
    margin-bottom: 0.3rem;
}
.alert-body {
    font-size: 0.85rem;
    opacity: 0.85;
    line-height: 1.5;
}

/* Metric boxes */
.metric-box {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 1.2rem;
    text-align: center;
}
.metric-value {
    font-size: 2rem;
    font-weight: 800;
}
.metric-label {
    font-size: 0.8rem;
    opacity: 0.6;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 0.2rem;
}

/* Powered by badges */
.powered-by {
    display: flex;
    gap: 0.6rem;
    flex-wrap: wrap;
    margin-top: 0.5rem;
}
.tech-badge {
    background: linear-gradient(135deg, rgba(239,68,68,0.15), rgba(239,68,68,0.05));
    border: 1px solid rgba(239,68,68,0.2);
    color: #fca5a5;
    padding: 0.3rem 0.8rem;
    border-radius: 8px;
    font-size: 0.72rem;
    font-weight: 600;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f0c29, #1a1744);
}
</style>
""", unsafe_allow_html=True)


# --- Header ---
st.markdown("""
<div class="main-header">
    <h1>💊 DrugLens</h1>
    <p>AI-Powered Polypharmacy Risk Analyzer for Elderly Care</p>
    <div class="badge-row">
        <span class="badge">🧠 MedGemma 4B</span>
        <span class="badge">🧬 TxGemma 2B</span>
        <span class="badge">✨ Gemma 4 31B</span>
        <span class="badge">🔴 AMD GPU Cloud</span>
        <span class="badge">🔥 Fireworks AI</span>
    </div>
</div>
""", unsafe_allow_html=True)


# --- Sidebar ---
with st.sidebar:
    st.markdown("### ⚙️ Configuration")

    use_llm = st.toggle("Use MedGemma Parser", value=False,
                         help="Parse medications with MedGemma AI. Disable for regex-only parsing.")
    use_txgemma = st.toggle("Use TxGemma Predictions", value=False,
                            help="Predict unknown drug interactions with TxGemma.")
    use_gemma4 = st.toggle("Use Gemma 4 Reports", value=True,
                           help="Generate AI-powered reports with Gemma 4 via Fireworks AI.")

    st.markdown("---")
    st.markdown("### 🧪 Demo Cases")
    st.markdown("Pre-loaded cases for testing:")

    demo_cases = get_demo_cases()
    selected_demo = st.selectbox(
        "Load a demo case",
        options=["— Select —"] + [c["name"] for c in demo_cases],
        index=0
    )

    if selected_demo != "— Select —":
        case = next(c for c in demo_cases if c["name"] == selected_demo)
        st.info(case["description"])

    st.markdown("---")
    st.markdown("### 📊 How It Works")
    st.markdown("""
    1. **Parse** — Extract medications from text
    2. **Check** — Drug interactions, Beers, STOPP/START
    3. **Predict** — AI-powered DDI prediction
    4. **Report** — Risk assessment & recommendations
    """)

    st.markdown("---")
    st.markdown("""
    <div class="powered-by">
        <span class="tech-badge">AMD Hackathon ACT II</span>
        <span class="tech-badge">Track 3 — Unicorn</span>
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
        options=[
            "Hypertension", "Diabetes Type 2", "Heart Failure", "Atrial Fibrillation",
            "COPD", "Osteoarthritis", "GERD", "Depression", "Anxiety", "Insomnia",
            "Chronic Kidney Disease", "Osteoporosis", "Dementia", "Parkinson's Disease",
            "Hypothyroidism", "Gout", "Epilepsy", "Asthma", "Coronary Artery Disease",
            "Peripheral Artery Disease", "DVT/PE", "Chronic Pain"
        ],
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


# --- Results Display ---
if "results" in st.session_state:
    results = st.session_state["results"]

    st.markdown("---")

    # --- Risk Overview ---
    risk_level = results.get("risk_level", "UNKNOWN")
    risk_score = results.get("risk_score", 0)
    risk_colors = {
        "HIGH": ("#ef4444", "risk-high"),
        "MODERATE": ("#f59e0b", "risk-moderate"),
        "LOW": ("#22c55e", "risk-low"),
        "MINIMAL": ("#06b6d4", "risk-minimal"),
    }
    color, css_class = risk_colors.get(risk_level, ("#9ca3af", "risk-minimal"))

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class="risk-card {css_class}">
            <p class="risk-score" style="color: {color};">{risk_level}</p>
            <p class="risk-label" style="color: {color};">Overall Risk</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        n_meds = len(results.get("parsed_medications", []))
        st.markdown(f"""
        <div class="metric-box">
            <p class="metric-value">{n_meds}</p>
            <p class="metric-label">Medications</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        n_interactions = len(results.get("interactions", []))
        st.markdown(f"""
        <div class="metric-box">
            <p class="metric-value" style="color: {'#ef4444' if n_interactions > 0 else '#22c55e'};">{n_interactions}</p>
            <p class="metric-label">Interactions Found</p>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        n_alerts = len(results.get("beers_alerts", [])) + len(results.get("stopp_start", {}).get("stopp", []))
        st.markdown(f"""
        <div class="metric-box">
            <p class="metric-value" style="color: {'#f59e0b' if n_alerts > 0 else '#22c55e'};">{n_alerts}</p>
            <p class="metric-label">Criteria Alerts</p>
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
            st.markdown("#### Database-Confirmed Interactions")
            for ix in interactions:
                sev = ix.get("severity", "moderate")
                css = f"alert-{sev}" if sev in ("high", "moderate", "low") else "alert-moderate"
                if sev == "major":
                    css = "alert-high"
                elif sev == "minor":
                    css = "alert-low"

                emoji = {"major": "🔴", "moderate": "🟡", "minor": "🟢"}.get(sev, "🟡")

                st.markdown(f"""
                <div class="alert-card {css}">
                    <div class="alert-title">{emoji} {ix.get('drug_a', '?')} ↔ {ix.get('drug_b', '?')} — {sev.upper()}</div>
                    <div class="alert-body">
                        <b>Effect:</b> {ix.get('effect', 'Unknown')}<br>
                        <b>Mechanism:</b> {ix.get('mechanism', 'Unknown')}<br>
                        <b>Management:</b> {ix.get('management', 'Consult prescriber')}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("No known drug interactions found in database.")

        if predicted:
            st.markdown("#### 🧬 TxGemma Predicted Interactions")
            for px_item in predicted:
                st.markdown(f"""
                <div class="alert-card alert-moderate">
                    <div class="alert-title">🤖 {px_item.get('drug_a', '?')} ↔ {px_item.get('drug_b', '?')} — AI PREDICTED</div>
                    <div class="alert-body">{px_item.get('predicted_interaction', 'Potential interaction predicted')}<br>
                    <b>Confidence:</b> {px_item.get('confidence', 'N/A')}</div>
                </div>
                """, unsafe_allow_html=True)

        # Interaction heatmap
        if interactions and len(results.get("parsed_medications", [])) >= 2:
            st.markdown("#### Interaction Matrix")
            meds = [m.get("name", m) if isinstance(m, dict) else str(m) for m in results["parsed_medications"]]
            n = len(meds)
            matrix = [[0]*n for _ in range(n)]

            for ix in interactions:
                da = normalize_drug_name(ix.get("drug_a", ""))
                db = normalize_drug_name(ix.get("drug_b", ""))
                for i, m in enumerate(meds):
                    for j, m2 in enumerate(meds):
                        nm1 = normalize_drug_name(m)
                        nm2 = normalize_drug_name(m2)
                        if (nm1 == da and nm2 == db) or (nm1 == db and nm2 == da):
                            sev_score = {"major": 3, "moderate": 2, "minor": 1}.get(ix.get("severity", "moderate"), 2)
                            matrix[i][j] = sev_score
                            matrix[j][i] = sev_score

            fig = go.Figure(data=go.Heatmap(
                z=matrix,
                x=meds,
                y=meds,
                colorscale=[
                    [0, "#1a1a2e"],
                    [0.33, "#22c55e"],
                    [0.66, "#f59e0b"],
                    [1, "#ef4444"]
                ],
                showscale=True,
                colorbar=dict(
                    title="Severity",
                    tickvals=[0, 1, 2, 3],
                    ticktext=["None", "Minor", "Moderate", "Major"]
                )
            ))
            fig.update_layout(
                title="Drug Interaction Heatmap",
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                height=400,
                font=dict(family="Inter")
            )
            st.plotly_chart(fig, use_container_width=True)

    # --- Beers Criteria Tab ---
    with tab_beers:
        beers = results.get("beers_alerts", [])
        if beers:
            st.markdown(f"#### {len(beers)} Beers Criteria Alert(s)")
            for alert in beers:
                sev = alert.get("severity", "moderate")
                css = f"alert-{sev}" if sev in ("high", "moderate", "low") else "alert-moderate"
                emoji = {"high": "🔴", "moderate": "🟡", "low": "🟢"}.get(sev, "🟡")

                rec = alert.get("recommendation", "Review")
                st.markdown(f"""
                <div class="alert-card {css}">
                    <div class="alert-title">{emoji} {alert.get('drug_class', 'Unknown')} — {rec}</div>
                    <div class="alert-body">
                        <b>Drugs matched:</b> {', '.join(alert.get('matched_drugs', []))}<br>
                        <b>Rationale:</b> {alert.get('rationale', 'N/A')}<br>
                        <b>Category:</b> {alert.get('category', 'N/A')}<br>
                        {f"<b>Exceptions:</b> {alert.get('exceptions')}" if alert.get('exceptions') else ""}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("No Beers Criteria alerts triggered.")

    # --- STOPP/START Tab ---
    with tab_stopp:
        stopp = results.get("stopp_start", {}).get("stopp", [])
        start = results.get("stopp_start", {}).get("start", [])

        if stopp:
            st.markdown(f"#### 🛑 {len(stopp)} STOPP Alert(s) — Consider Stopping")
            for rule in stopp:
                st.markdown(f"""
                <div class="alert-card alert-high">
                    <div class="alert-title">🛑 [{rule.get('id', '')}] {rule.get('category', '')}</div>
                    <div class="alert-body">
                        <b>Criteria:</b> {rule.get('criteria', '')}<br>
                        <b>Drugs matched:</b> {', '.join(rule.get('matched_drugs', []))}<br>
                        <b>Rationale:</b> {rule.get('rationale', '')}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("No STOPP criteria triggered.")

        if start:
            st.markdown(f"#### ✅ {len(start)} START Suggestion(s) — Consider Starting")
            for rule in start:
                st.markdown(f"""
                <div class="alert-card alert-low">
                    <div class="alert-title">✅ [{rule.get('id', '')}] {rule.get('category', '')}</div>
                    <div class="alert-body">
                        <b>Criteria:</b> {rule.get('criteria', '')}<br>
                        <b>Suggested drugs:</b> {', '.join(rule.get('drugs', []))}<br>
                        <b>Rationale:</b> {rule.get('rationale', '')}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No START suggestions applicable.")

    # --- AI Report Tab ---
    with tab_report:
        report = results.get("risk_report", {})
        if report:
            if report.get("summary"):
                st.markdown("#### 📝 Summary")
                st.info(report["summary"])

            if report.get("clinical_summary"):
                st.markdown("#### 🏥 Clinical Summary")
                st.markdown(report["clinical_summary"])

            if report.get("deprescribing_suggestions"):
                st.markdown("#### 💊 Deprescribing Suggestions")
                for sug in report["deprescribing_suggestions"]:
                    st.markdown(f"""
                    <div class="alert-card alert-moderate">
                        <div class="alert-title">💊 Consider stopping: {sug.get('drug', '?')}</div>
                        <div class="alert-body">
                            <b>Reason:</b> {sug.get('reason', '')}<br>
                            <b>Alternative:</b> {sug.get('alternative', 'Discuss with prescriber')}<br>
                            <b>Priority:</b> {sug.get('priority', 'Medium')}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            if report.get("recommendations"):
                st.markdown("#### ✅ Recommendations")
                for rec in report["recommendations"]:
                    st.markdown(f"- {rec}")

            if report.get("patient_summary"):
                st.markdown("#### 👤 Patient-Friendly Summary")
                st.success(report["patient_summary"])
        else:
            st.info("Enable Gemma 4 in settings for AI-powered reports, or run analysis first.")

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
st.markdown("---")
st.markdown("""
<div style="text-align: center; opacity: 0.5; font-size: 0.8rem; padding: 1rem 0;">
    <p>DrugLens — AMD Developer Hackathon: ACT II | Track 3 Unicorn Track</p>
    <p>⚠️ For educational and research purposes only. Not a substitute for professional medical advice.</p>
    <p>Powered by MedGemma · TxGemma · Gemma 4 · AMD Developer Cloud · Fireworks AI</p>
</div>
""", unsafe_allow_html=True)
