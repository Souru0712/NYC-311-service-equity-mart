import streamlit as st

_CSS = """
<style>
/* ── Layout ──────────────────────────────────────────────────────────────── */
.block-container {
    padding: 2rem 3rem 4rem;
    max-width: 1200px;
}

/* ── Typography ──────────────────────────────────────────────────────────── */
h1 {
    font-size: 2rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.3px;
    color: #F0F4FF !important;
}
h2, h3 {
    font-weight: 600 !important;
    color: #F0F4FF !important;
}
h3 { font-size: 1.15rem !important; }

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #0D1220 !important;
    border-right: 1px solid #1E2940;
}
[data-testid="stSidebarNav"] a {
    font-size: 0.92rem;
    font-weight: 500;
}

/* ── Metric cards ────────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background-color: #141B2D;
    border: 1px solid #1E2940;
    border-left: 4px solid #4CC9F0;
    border-radius: 8px;
    padding: 1rem 1.25rem !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.8rem !important;
    font-weight: 700 !important;
    color: #F0F4FF !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.78rem !important;
    color: #8892A4 !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
[data-testid="stMetricDelta"] {
    font-size: 0.85rem !important;
}

/* ── Dividers ────────────────────────────────────────────────────────────── */
hr {
    border-color: #1E2940 !important;
    margin: 1.8rem 0 !important;
}

/* ── Expanders ───────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    border: 1px solid #1E2940 !important;
    border-radius: 8px !important;
    background-color: #141B2D !important;
}
[data-testid="stExpander"] summary {
    font-weight: 500;
    color: #8892A4;
    font-size: 0.88rem;
}

/* ── Info / alert boxes ──────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 8px !important;
    border: 1px solid #1E2940 !important;
}
[data-testid="stAlert"][kind="info"] {
    background-color: #0D1B2E !important;
    border-left: 4px solid #4CC9F0 !important;
}
[data-testid="stAlert"][kind="warning"] {
    border-left: 4px solid #F4A261 !important;
}
[data-testid="stAlert"][kind="error"] {
    border-left: 4px solid #E63946 !important;
}
[data-testid="stAlert"][kind="success"] {
    border-left: 4px solid #2DC653 !important;
}

/* ── Captions ────────────────────────────────────────────────────────────── */
[data-testid="stCaptionContainer"] p {
    color: #8892A4 !important;
    font-size: 0.8rem !important;
}

/* ── Selectbox / multiselect ─────────────────────────────────────────────── */
[data-testid="stSelectbox"] > div,
[data-testid="stMultiSelect"] > div {
    border-radius: 6px !important;
}

/* ── Radio buttons ───────────────────────────────────────────────────────── */
[data-testid="stRadio"] label {
    font-size: 0.9rem !important;
}

/* ── Tables (st.table) ───────────────────────────────────────────────────── */
table {
    font-size: 0.85rem !important;
    border-collapse: collapse;
}
thead tr th {
    background-color: #141B2D !important;
    color: #8892A4 !important;
    font-size: 0.75rem !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid #1E2940 !important;
}
tbody tr:nth-child(even) td {
    background-color: #0D1220 !important;
}
tbody tr:hover td {
    background-color: #141B2D !important;
}

/* ── Spinner ─────────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] {
    color: #4CC9F0 !important;
}

/* ── AI synthesis callout ────────────────────────────────────────────────── */
.synthesis-box {
    background-color: #0D1B2E;
    border: 1px solid #1E2940;
    border-left: 4px solid #4CC9F0;
    border-radius: 8px;
    padding: 1.5rem 2rem;
    margin-top: 0.5rem;
    line-height: 1.7;
}
.synthesis-box h2, .synthesis-box h3,
.synthesis-box strong {
    color: #F0F4FF !important;
}

/* ── Hero stats (landing page) ───────────────────────────────────────────── */
.hero-stat {
    background: linear-gradient(135deg, #141B2D 0%, #0D1220 100%);
    border: 1px solid #1E2940;
    border-radius: 10px;
    padding: 1.5rem;
    text-align: center;
}
.hero-stat .number {
    font-size: 2.4rem;
    font-weight: 800;
    color: #4CC9F0;
    line-height: 1;
}
.hero-stat .label {
    font-size: 0.82rem;
    color: #8892A4;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-top: 0.4rem;
}
</style>
"""


def inject_css() -> None:
    """Inject the global NYC Civic Dark stylesheet. Call once at the top of every page."""
    st.markdown(_CSS, unsafe_allow_html=True)
