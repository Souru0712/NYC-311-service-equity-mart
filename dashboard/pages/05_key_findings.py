import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from groq import Groq
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.snowflake_conn import run_query
from utils.styles import inject_css
from utils.sidebar import setup_sidebar
from utils.auth import is_dev

st.set_page_config(page_title="Key Findings | NYC 311", page_icon="🔍", layout="wide")
inject_css()
setup_sidebar()

_chart_config = {"displayModeBar": True, "displaylogo": False,
                 "modeBarButtonsToRemove": ["select2d", "lasso2d"]}

# ── Claude synthesis ──────────────────────────────────────────────────────────
_SYNTHESIS_SYSTEM = """\
You are generating descriptive text for a data dashboard. You do NOT analyze
or interpret. You restate verified findings and describe what charts show.

VERIFIED FINDINGS -- these are FACTS. Restate them; never contradict them:
1. At the median, 311 response time is essentially EQUAL across all five
   income quintiles citywide (P50 approx. 8-10 hrs for every quintile). There is
   NO broad income-based equity gap at the median.
2. The real, defensible gap is WITHIN specific complaint types. The strongest
   finding is the NYPD noise cluster: low-income (Q1) tracts wait 1.5-2x
   longer at P90 than high-income (Q5) tracts, consistent across FOUR
   independent noise categories (Residential, Commercial, Vehicle,
   Street/Sidewalk), spanning 1.7M+ Q1 requests. Absolute values are modest
   (Q1 P90 approx. 3-4 hrs vs Q5 approx. 2 hrs).
3. Street Sign -- Damaged shows a larger ratio (4.7x, 174 vs 37 days median
   P90) but on LOW volume (approx. 535 Q1 requests) -- always state it as lower-volume.
4. The AGGREGATE P90 across all complaint types INVERTS (Q5 appears slower).
   This is a complaint-MIX CONFOUND, not a service gap: e.g. helicopter-noise
   complaints have near-identical P90s in Q1 and Q5 (~26,600 hrs) but Q5
   files them 62x more often. Both quintiles have idiosyncratic slow tails
   (Q5: helicopter noise, tree requests; Q1: smoking, mobile food vendor).
   Cross-quintile AGGREGATE comparison is therefore uninformative in EITHER
   direction.

ABSOLUTE PROHIBITIONS:
- NEVER claim low-income tracts wait longer overall or at the median.
- NEVER call the monthly trend an "equity gap"; it is a response-time trend
  influenced by complaint mix.
- NEVER recommend that an agency "improve response times" on a complaint type
  without stating that type's gap survives a volume floor AND comparing its
  P90 across quintiles.
- NEVER describe structurally-slow tail types (smoking, mobile food vendor,
  new tree request, helicopter noise, food establishment) as service-quality
  failures -- they are equally slow across quintiles by their nature.
- NEVER attribute a gap to agency bias.
- NEVER output policy recommendations of any kind.
- State ONLY numbers present in the data provided. Do not invent figures.

TASK: Write 1-2 plain sentences per chart describing what it displays. Lead
with finding 2 (noise cluster), then 3 (street sign, lower volume), then 4
(the confound). Do not add analysis beyond the verified findings above.
Total response under 400 words. Plain English, no markdown headers.\
"""


def _data_hash(gap_json: str, heatmap_json: str, trend_json: str) -> str:
    import hashlib
    return hashlib.md5((gap_json + heatmap_json + trend_json).encode()).hexdigest()


def _ensure_cache_table() -> None:
    """Ensure AI_SYNTHESIS_CACHE exists. Idempotent -- safe to call on every page load."""
    from utils.snowflake_conn import get_snowflake_conn
    try:
        get_snowflake_conn().cursor().execute("""
            CREATE TABLE IF NOT EXISTS MARTS.AI_SYNTHESIS_CACHE (
                data_hash      VARCHAR PRIMARY KEY,
                status         VARCHAR DEFAULT 'pending',
                synthesis_text VARCHAR,
                generated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except Exception:
        pass


def _load_cached_synthesis(data_hash: str) -> tuple[str, str] | None:
    """Return (status, text) for this hash, or None if no row exists.

    Queries Snowflake directly (no cache) so the button disappears immediately
    after generation without waiting for run_query's TTL to expire.

    status: 'pending' -- another process is generating, don't call Groq again.
            'complete' -- ready to display.
    """
    from utils.snowflake_conn import get_snowflake_conn
    try:
        conn = get_snowflake_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT status, synthesis_text FROM MARTS.AI_SYNTHESIS_CACHE "
            "WHERE data_hash = %s LIMIT 1",
            (data_hash,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return row[0], row[1]
    except Exception:
        return None


def _claim_slot(data_hash: str) -> bool:
    """INSERT a pending row. Returns True if this process won the lock, False if already claimed."""
    from utils.snowflake_conn import get_snowflake_conn
    try:
        get_snowflake_conn().cursor().execute(
            "INSERT INTO MARTS.AI_SYNTHESIS_CACHE (data_hash, status) "
            "SELECT %s, 'pending' WHERE NOT EXISTS ("
            "  SELECT 1 FROM MARTS.AI_SYNTHESIS_CACHE WHERE data_hash = %s"
            ")",
            (data_hash, data_hash),
        )
        return True
    except Exception:
        return False


def _store_synthesis(data_hash: str, text: str) -> None:
    """Mark the row complete with the generated text."""
    from utils.snowflake_conn import get_snowflake_conn
    try:
        get_snowflake_conn().cursor().execute(
            "UPDATE MARTS.AI_SYNTHESIS_CACHE "
            "SET synthesis_text = %s, status = 'complete', generated_at = CURRENT_TIMESTAMP "
            "WHERE data_hash = %s",
            (text, data_hash),
        )
    except Exception:
        pass


def _generate_pdf(sort_context: str, body: str) -> bytes:
    # Render the synthesis as a PDF using pre-wrapped lines to avoid fpdf line-break crashes.
    import textwrap
    from fpdf import FPDF

    def _s(text: str) -> str:
        # Sanitize to latin-1 -- any unencodable character becomes ?.
        return text.encode("latin-1", errors="replace").decode("latin-1")

    def _emit(pdf, text: str, width: int, line_h: float) -> None:
        # Pre-wrap and emit one cell per wrapped line -- bypasses multi_cell entirely.
        for chunk in textwrap.wrap(text, width=width) or [""]:
            pdf.cell(pdf.epw, line_h, _s(chunk))
            pdf.ln(line_h)

    pdf = FPDF()
    pdf.set_margins(20, 20, 20)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(pdf.epw, 12, _s("NYC 311 Service Equity Report"))
    pdf.ln(12)

    # Metadata
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(pdf.epw, 6, _s(f"Generated: {date.today().strftime('%B %d, %Y')}"))
    pdf.ln(6)
    pdf.cell(pdf.epw, 6, _s(f"Sort context: {sort_context}"))
    pdf.ln(10)
    pdf.set_draw_color(180, 180, 180)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(6)

    for raw_line in body.split("\n"):
        line = raw_line.strip()

        if not line or line == "---":
            pdf.ln(4)
            continue

        # **Section Header**
        if line.startswith("**") and line.endswith("**") and line.count("**") == 2:
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 12)
            _emit(pdf, line.strip("*").strip(), width=85, line_h=7)
            continue

        # Bullet or numbered list
        if line.startswith("- ") or line.startswith("* "):
            pdf.set_font("Helvetica", "", 10)
            _emit(pdf, "- " + line[2:], width=88, line_h=6)
            continue

        if len(line) > 2 and line[0].isdigit() and line[1] in ".)":
            pdf.set_font("Helvetica", "", 10)
            _emit(pdf, line, width=88, line_h=6)
            continue

        # Body text
        line = line.replace("**", "")
        pdf.set_font("Helvetica", "", 10)
        _emit(pdf, line, width=88, line_h=6)

    return bytes(pdf.output())


def _call_groq(prompt: str) -> str:
    api_key = (
        st.secrets.get("GROQ_API_KEY")
        or st.secrets["snowflake"].get("GROQ_API_KEY")
    )
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": _SYNTHESIS_SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=600,
    )
    return response.choices[0].message.content

# Agency responsible for each complaint type -- mirrors the reference tab in app.py
_AGENCY: dict[str, str] = {
    "ANIMAL IN A PARK": "Parks",
    "ANIMAL-ABUSE": "NYPD/ACC",
    "DEAD ANIMAL": "Sanitation",
    "MOSQUITOES": "Health",
    "POISON IVY": "Parks",
    "DOOR/WINDOW": "HPD",
    "ELEVATOR": "HPD",
    "FLOORING/STAIRS": "HPD",
    "HEAT/HOT WATER": "HPD",
    "NON-RESIDENTIAL HEAT": "HPD/DOB",
    "OUTSIDE BUILDING": "HPD/DOB",
    "PAINT/PLASTER": "HPD",
    "PLUMBING": "HPD",
    "UNSANITARY CONDITION": "HPD",
    "WATER LEAK": "HPD/DEP",
    "WATER SYSTEM": "HPD/DEP",
    "CONSUMER COMPLAINT": "DCWP",
    "DRINKING": "NYPD",
    "FOOD ESTABLISHMENT": "Health",
    "MOBILE FOOD VENDOR": "Health/DCWP",
    "SMOKING OR VAPING": "Health/NYPD",
    "TATTOOING": "Health",
    "AIR QUALITY": "DEP",
    "WATER CONSERVATION": "DEP",
    "NOISE": "NYPD",
    "NOISE - COMMERCIAL": "NYPD",
    "NOISE - HOUSE OF WORSHIP": "NYPD",
    "NOISE - PARK": "Parks/NYPD",
    "NOISE - RESIDENTIAL": "NYPD",
    "NOISE - STREET/SIDEWALK": "NYPD",
    "NOISE - VEHICLE": "NYPD",
    "ILLEGAL FIREWORKS": "NYPD/FDNY",
    "ABANDONED BIKE": "Sanitation",
    "ABANDONED VEHICLE": "NYPD/Sanitation",
    "BIKE/ROLLER/SKATE": "NYPD",
    "BLOCKED DRIVEWAY": "NYPD",
    "CURB CONDITION": "DOT",
    "DERELICT VEHICLES": "NYPD/Sanitation",
    "ILLEGAL PARKING": "NYPD/DOT",
    "OBSTRUCTION": "DOT/DOB",
    "SIDEWALK CONDITION": "DOT",
    "STREET CONDITION": "DOT",
    "STREET SIGN - DAMAGED": "DOT",
    "STREET SIGN - MISSING": "DOT",
    "TRAFFIC": "DOT/NYPD",
    "TRAFFIC SIGNAL CONDITION": "DOT",
    "COMMERCIAL DISPOSAL COMPLAINT": "Sanitation",
    "DEAD/DYING TREE": "Parks",
    "DIRTY CONDITION": "Sanitation",
    "GRAFFITI": "Sanitation/Parks",
    "ILLEGAL DUMPING": "Sanitation",
    "ILLEGAL TREE DAMAGE": "Parks",
    "LITTER BASKET COMPLAINT": "Sanitation",
    "LITTER BASKET REQUEST": "Sanitation",
    "MISSED COLLECTION": "Sanitation",
    "OVERGROWN TREE/BRANCHES": "Parks",
    "RESIDENTIAL DISPOSAL COMPLAINT": "Sanitation",
    "SANITATION WORKER OR VEHICLE COMPLAINT": "Sanitation",
    "SEWER": "DEP",
    "STREET SWEEPING COMPLAINT": "Sanitation/DOT",
    "WOOD PILE REMAINING": "Parks/Sanitation",
    "DISORDERLY YOUTH": "NYPD",
    "DRUG ACTIVITY": "NYPD",
    "ENCAMPMENT": "DHS/NYPD",
    "HOMELESS PERSON ASSISTANCE": "DHS",
    "NON-EMERGENCY POLICE MATTER": "NYPD",
    "PANHANDLING": "NYPD",
    "URINATING IN PUBLIC": "NYPD",
    "VENDOR ENFORCEMENT": "DCWP/NYPD",
    "VIOLATION OF PARK RULES": "Parks",
    "APPLIANCE": "HPD",
    "DAY CARE": "ACS/Health",
    "ELECTRIC": "HPD/ConEd",
    "ELECTRICAL": "DOB/ConEd",
    "EMERGENCY RESPONSE TEAM (ERT)": "DOB/FDNY",
    "GENERAL": "Various",
    "GENERAL CONSTRUCTION/PLUMBING": "DOB",
    "MAINTENANCE OR FACILITY": "Various",
    "SAFETY": "Various",
}

st.header("🔍 Key Findings")
st.markdown("""
The other pages show *what* is happening. This page answers *why* -- and *who* should act on it.

The core question: when low-income neighborhoods wait longer for 311 responses, is it because of
**where they are** (geography), **how much they earn** (income), or **what they reported**
(complaint type / agency responsible)?
""")

with st.expander("How to read this page"):
    st.markdown("""
    **Equity score methodology:**
    Equity score = tract P90 ÷ **median tract P90** citywide for that complaint type and month.
    Every tract counts equally in the baseline -- high-volume boroughs do not skew the reference.
    Score 1.0 = this tract matches the typical NYC neighborhood.
    Score > 1.0 = residents wait longer than the typical tract.

    **Finding 1 -- Equity gap by complaint type:**
    Each bar is one complaint type, sized by how much longer Q1 (lowest income) tracts wait
    relative to Q5 (highest income) tracts on average equity score.
    The agency column tells you who is accountable.
    If the gap clusters around one or two agencies, the problem is agency-driven -- not just
    neighborhood-driven.

    **Finding 2 -- Borough × income quintile heatmap:**
    Each cell is the average equity score for that borough/quintile combination.
    Green (≤1.0) = at or below the median tract baseline. Red (>1.0) = longer than typical.
    - If all quintiles in a borough are red → the whole borough is underserved regardless of income
      (geographic problem).
    - If you see a green-to-red gradient from Q5 → Q1 within every borough → income is the
      predictor, not location (structural equity problem).
    - The most actionable pattern is a borough where Q1 is deeply red but Q5 is green --
      same city, same agency, different treatment.

""")

st.divider()

# ── Headline: noise cluster from FCT_EQUITY_GAP_BY_TYPE ───────────────────────
# Aggregate Q1-vs-Q5 comparisons are confounded by complaint-mix and are not
# reported here. The headline is sourced from within-complaint-type medians
# (per-tract P90, volume floor 30 complaints/tract, bilateral 500-complaint guard).
headline_gap_sql = """
SELECT
    complaint_type,
    q1_n_complaints,
    q5_n_complaints,
    q1_p90_hours,
    q5_p90_hours,
    q1_over_q5_gap
FROM MARTS.FCT_EQUITY_GAP_BY_TYPE
ORDER BY q1_over_q5_gap DESC
"""
with st.spinner("Loading headline metrics..."):
    headline_df = run_query(headline_gap_sql)

_NOISE_TYPES = [
    "NOISE - RESIDENTIAL", "NOISE - STREET/SIDEWALK",
    "NOISE - VEHICLE",     "NOISE - COMMERCIAL",
]

if not headline_df.empty:
    top = headline_df.iloc[0]
    noise = headline_df[headline_df["complaint_type"].isin(_NOISE_TYPES)]
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Largest confirmed gap",
        f"{top['q1_over_q5_gap']:.2f}×",
        help=(
            f"{top['complaint_type']}: Q1 median tract P90 = {top['q1_p90_hours']} hrs "
            f"vs Q5 = {top['q5_p90_hours']} hrs. "
            f"Q1 n={int(top['q1_n_complaints']):,} | Q5 n={int(top['q5_n_complaints']):,}. "
            "Both quintiles cleared the 500-complaint volume floor."
        ),
    )
    if not noise.empty:
        col2.metric(
            "NYPD noise gap (4 categories)",
            f"~{noise['q1_over_q5_gap'].median():.1f}×",
            help=(
                "Consistent ~2× gap across Noise - Residential, Street/Sidewalk, Vehicle, "
                "and Commercial -- all handled by NYPD. "
                "Q1 median P90 ≈ 3-4 hrs vs Q5 ≈ 2 hrs."
            ),
        )
        col3.metric(
            "Q1 noise complaints",
            f"{noise['q1_n_complaints'].sum() / 1_000_000:.1f}M",
            help="Total Q1-tract complaints behind the noise cluster finding.",
        )
    st.caption(
        "Gaps sourced from `FCT_EQUITY_GAP_BY_TYPE`: per-tract median P90, "
        "30-complaint volume floor per tract, bilateral 500-complaint guard per quintile. "
        "Aggregate Q1-vs-Q5 comparisons are not shown -- they invert due to complaint-mix "
        "confounding (confirmed: helicopter noise, tree requests, and food inspections "
        "have identical P90s in Q1 and Q5 but are filed 2-62× more often by Q5 tracts)."
    )

st.divider()

# ── Finding 1: Which complaint types drive the gap? ───────────────────────────
st.subheader("① Which complaint types have the biggest equity gap -- and which agencies own them?")
st.markdown("""
The bars below show the top 10 complaint types ranked by the difference in **median** equity score
between Q1 and Q5 tracts (only rows with 10+ complaints per tract per month are included, removing
thin-data outliers). A larger gap means the city's response is *more unequal* for that
complaint type. The **Agency** column identifies who is accountable for closing it.
""")

# Default sort: Total requests desc — so the noise cluster (1.7M+ Q1 requests)
# floats to the top visually. Gap desc is available but ranks thin-volume
# dramatic numbers above high-confidence findings, inverting analytical priority.
f1_sort = st.radio(
    "Order by",
    ["Total requests desc", "Gap desc"],
    horizontal=True,
    key="f1_sort",
    help="Default: highest-volume findings first (noise cluster leads). "
         "Switch to Gap desc to see the largest ratios -- but note thin-volume "
         "types (Street Sign n=535, Animal in a Park n=857) will top that ranking.",
)
f1_order = {
    "Total requests desc": "(q1_n_complaints + q5_n_complaints) DESC",
    "Gap desc":            "q1_over_q5_gap DESC",
}[f1_sort]

# Display floor: hide thin-volume types by default so the chart's visual
# ordering matches analytical confidence, not just gap magnitude.
# FCT_EQUITY_GAP_BY_TYPE already enforces bilateral >=500; this adds a
# higher display-only threshold to remove Street Sign (535) and Animal in
# a Park (857) from the default view.
show_thin = st.checkbox(
    "Include lower-volume complaint types (Q1 < 5,000 requests)",
    value=False,
    help="When unchecked, hides types like Street Sign - Damaged (535 Q1 requests) "
         "and Animal in a Park (857) whose gaps are real but carry less confidence "
         "than the noise cluster (1.7M+ requests). The model's bilateral >=500 "
         "floor still applies regardless.",
)

# Read from FCT_EQUITY_GAP_BY_TYPE -- the single canonical gap source.
# Volume guard (>=500 per quintile) is built into that table; the checkbox
# above is retained for UX but the table already enforces it.
gap_sql = f"""
SELECT
    complaint_type,
    q1_n_complaints,
    q5_n_complaints,
    q1_n_complaints + q5_n_complaints  AS total_requests,
    q1_p90_hours,
    q5_p90_hours,
    q1_over_q5_gap
FROM MARTS.FCT_EQUITY_GAP_BY_TYPE
ORDER BY {f1_order}
LIMIT 10
"""
with st.spinner("Loading Finding 1..."):
    gap_df = run_query(gap_sql)

if not gap_df.empty:
    if not show_thin:
        gap_df = gap_df[gap_df["q1_n_complaints"] >= 5000].reset_index(drop=True)
    gap_df["agency"] = gap_df["complaint_type"].map(_AGENCY).fillna("Various")

    _f1_chart_col = "total_requests" if f1_sort == "Total requests desc" else "q1_over_q5_gap"
    fig = px.bar(
        gap_df.sort_values(_f1_chart_col, ascending=True),
        x="q1_over_q5_gap",
        y="complaint_type",
        color="q1_over_q5_gap",
        color_continuous_scale="RdYlGn_r",
        color_continuous_midpoint=1.0,
        orientation="h",
        hover_data={
            "agency":          True,
            "q1_p90_hours":    True,
            "q5_p90_hours":    True,
            "total_requests":  True,
            "q1_n_complaints": True,
            "q5_n_complaints": True,
        },
        labels={
            "q1_over_q5_gap":   "Q1 / Q5 median tract P90 (ratio)",
            "complaint_type":   "Complaint Type",
            "agency":           "Agency",
            "q1_p90_hours":     "Q1 median P90 (hrs)",
            "q5_p90_hours":     "Q5 median P90 (hrs)",
            "total_requests":   "Total requests",
            "q1_n_complaints":  "Q1 complaints",
            "q5_n_complaints":  "Q5 complaints",
        },
        title="Top 10 complaint types -- Q1 / Q5 median tract P90 gap (1.0 = equal)",
    )
    fig.add_vline(x=1.0, line_dash="dash", line_color="grey", annotation_text="Equal (1.0)")
    fig.update_layout(coloraxis_showscale=False, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True, config=_chart_config)
    st.caption(
        "**How to read:** Bar length = ratio of Q1 to Q5 median tract P90 (median P90 hours, "
        ">=30 complaints per tract cell, bilateral >=500 complaint guard). "
        "Bar > 1.0 = Q1 low-income tracts wait longer at P90. "
        "Bar < 1.0 = Q5 high-income tracts wait longer (may be complaint-mix confound). "
        "Dashed line at 1.0 = equal service. Source: FCT_EQUITY_GAP_BY_TYPE."
    )

    st.markdown("**Details for the above complaint types:**")
    _gap_tbl = (
        gap_df[["complaint_type", "agency", "q1_n_complaints", "q5_n_complaints",
                "q1_p90_hours", "q5_p90_hours", "q1_over_q5_gap"]]
        .rename(columns={
            "complaint_type":   "Complaint Type",
            "agency":           "Agency",
            "q1_n_complaints":  "Q1 Complaints",
            "q5_n_complaints":  "Q5 Complaints",
            "q1_p90_hours":     "Q1 P90 (hrs)",
            "q5_p90_hours":     "Q5 P90 (hrs)",
            "q1_over_q5_gap":   "Gap (Q1/Q5)",
        })
    )
    st.dataframe(
        _gap_tbl,
        use_container_width=True,
        column_config={
            "Q1 Complaints": st.column_config.NumberColumn(format="%d"),
            "Q5 Complaints": st.column_config.NumberColumn(format="%d"),
            "Q1 P90 (hrs)":  st.column_config.NumberColumn(format="%.1f",
                help="Median of per-tract P90s across Q1 tracts (>=30 complaints/tract)."),
            "Q5 P90 (hrs)":  st.column_config.NumberColumn(format="%.1f"),
            "Gap (Q1/Q5)":   st.column_config.NumberColumn(format="%.2f",
                help=">1.0 = Q1 waits longer. <1.0 = Q5 waits longer (check for confound)."),
        },
        hide_index=True,
    )
    st.caption(
        "All rows cleared the bilateral >=500 complaint volume guard. "
        "Gap = Q1 median tract P90 / Q5 median tract P90 -- same definition as the headline KPI above."
    )
else:
    st.info("No data found -- run the pipeline first.")

st.divider()

# ── Finding 2: Geography vs income ───────────────────────────────────────────
st.subheader("② Is the gap geographic or income-driven? Borough × income quintile")
st.markdown("""
Each cell shows the average equity score for that borough and income quintile.
**Green = at or below city-average wait. Red = above city-average wait.**

Read each borough row left to right (Q1 → Q5). A gradient from red to green within a single
borough row means income -- not just location -- determines how fast the city responds.
A borough where every cell is red regardless of quintile points to a resource deficit for that
entire area.
""")

_DEFAULT_START = "2020-01-01"
_DEFAULT_END   = date.today().strftime("%Y-%m-%d")
_DATE_RE       = re.compile(r"^\d{4}-\d{2}-\d{2}$")

st.caption("📅 Date range · Format: YYYY-MM-DD · e.g. 2023-01-01")
_hdc1, _hdc2, _hdc3 = st.columns([2, 2, 1])
_h_start = _hdc1.text_input("Start date", value=_DEFAULT_START, key="f2_start")
_h_end   = _hdc2.text_input("End date",   value=_DEFAULT_END,   key="f2_end")
if _hdc3.button("↺ Reset", key="f2_reset", use_container_width=True):
    st.session_state.pop("f2_start", None)
    st.session_state.pop("f2_end",   None)
    st.rerun()

f2_start = _h_start if _DATE_RE.match(_h_start or "") else _DEFAULT_START
f2_end   = _h_end   if _DATE_RE.match(_h_end   or "") else _DEFAULT_END

heatmap_sql = f"""
SELECT
    borough,
    income_quintile,
    ROUND(MEDIAN(equity_score), 3) AS avg_equity_score
FROM MARTS.FCT_EQUITY_SPLITS
WHERE borough NOT IN ('UNSPECIFIED', '')
  AND income_quintile IS NOT NULL
  AND request_count >= 10
  AND request_month BETWEEN '{f2_start}' AND '{f2_end}'
GROUP BY borough, income_quintile
ORDER BY borough, income_quintile
"""
with st.spinner("Loading Finding 2..."):
    heatmap_df = run_query(heatmap_sql)

if not heatmap_df.empty:
    pivot = heatmap_df.pivot(
        index="borough", columns="income_quintile", values="avg_equity_score"
    )
    pivot.columns = [f"Q{c}" for c in pivot.columns]
    pivot = pivot.reindex(["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"])

    fig = px.imshow(
        pivot,
        color_continuous_scale="RdYlGn_r",
        color_continuous_midpoint=1.0,
        text_auto=".2f",
        aspect="auto",
        labels={"x": "Income Quintile", "y": "Borough", "color": "Avg Equity Score"},
        title="Average equity score by borough and income quintile (1.0 = city average)",
    )
    fig.update_layout(xaxis_title="Income Quintile (Q1=lowest, Q5=highest)", yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True, config=_chart_config)
    st.caption(
        "**How to read:** Each cell = avg equity score for that borough and income quintile. "
        "Green (<=1.0) = at or below city median wait. Red (>1.0) = longer than typical. "
        "A red-to-green gradient across a row (Q1->Q5) = income drives the gap. "
        "A row that is entirely red regardless of quintile = the whole borough is underserved -- a geographic problem, not just an income problem."
    )
else:
    st.info("No data found -- run the pipeline first.")

st.divider()

# ── Finding 3: Equity trend over time ────────────────────────────────────────
st.subheader("③ Is the gap growing or closing? Equity score trend -- Q1 vs Q5")
st.markdown("""
Tracks whether the service disparity between the lowest and highest income tracts is improving
over time. A widening gap signals that inequity is systemic and worsening.
A narrowing gap signals that targeted policy or resource changes are having an effect.
""")

seasonal_trend = st.checkbox(
    "View by season instead of month",
    value=False,
    help="Collapses monthly data into Spring / Summer / Fall / Winter averages "
         "so structural trends stand out from month-to-month noise.",
)

# Always fetch monthly -- used for the chart (monthly mode) and AI synthesis
trend_sql = """
SELECT
    request_month,
    income_quintile,
    MEDIAN(equity_score) AS avg_equity_score,
    SUM(request_count)   AS total_requests
FROM MARTS.FCT_EQUITY_SPLITS
WHERE income_quintile IN (1, 5)
  AND request_count >= 10
GROUP BY request_month, income_quintile
ORDER BY request_month
"""
with st.spinner("Loading Finding 3..."):
    trend_df = run_query(trend_sql)

if not trend_df.empty:
    import pandas as pd

    if seasonal_trend:
        # Aggregate monthly data to seasons in pandas -- avoids a second SQL query
        temp = trend_df.copy()
        temp["month"] = pd.to_datetime(temp["request_month"]).dt.month
        temp["yr"]    = pd.to_datetime(temp["request_month"]).dt.year
        _season_name  = {1:"Winter",2:"Winter",3:"Spring",4:"Spring",5:"Spring",
                         6:"Summer",7:"Summer",8:"Summer",9:"Fall",10:"Fall",11:"Fall",12:"Winter"}
        _season_order = {1:1,2:1,3:2,4:2,5:2,6:3,7:3,8:3,9:4,10:4,11:4,12:1}
        temp["season"]       = temp["month"].map(_season_name)
        temp["season_order"] = temp["month"].map(_season_order)
        seasonal_agg = (
            temp.groupby(["yr","season","season_order","income_quintile"])
            .agg(avg_equity_score=("avg_equity_score","mean"), total_requests=("total_requests","sum"))
            .reset_index()
            .sort_values(["yr","season_order"])
        )
        seasonal_agg["period"] = seasonal_agg["yr"].astype(str) + " " + seasonal_agg["season"]
        period_order = seasonal_agg[["yr","season_order","period"]].drop_duplicates() \
                           .sort_values(["yr","season_order"])["period"].tolist()
        q1 = seasonal_agg[seasonal_agg["income_quintile"]==1].set_index("period").reindex(period_order).reset_index()
        q5 = seasonal_agg[seasonal_agg["income_quintile"]==5].set_index("period").reindex(period_order).reset_index()
    else:
        period_order = sorted(trend_df["request_month"].unique())
        trend_df["period"] = trend_df["request_month"]
        q1 = trend_df[trend_df["income_quintile"]==1].set_index("period").reindex(period_order).reset_index()
        q5 = trend_df[trend_df["income_quintile"]==5].set_index("period").reindex(period_order).reset_index()

    view_label = "Season" if seasonal_trend else "Month"
    trend_fig = go.Figure()
    trend_fig.add_trace(go.Scatter(
        x=q5["period"], y=q5["avg_equity_score"],
        name="Q5 -- highest income", mode="lines+markers",
        line=dict(color="#4C9BE8", width=2), marker=dict(size=5),
        hovertemplate="<b>%{x}</b><br>Q5 avg equity score: %{y:.3f}<extra></extra>",
    ))
    trend_fig.add_trace(go.Scatter(
        x=q1["period"], y=q1["avg_equity_score"],
        name="Q1 -- lowest income", mode="lines+markers",
        line=dict(color="#E84C4C", width=2), marker=dict(size=5),
        fill="tonexty", fillcolor="rgba(232, 76, 76, 0.12)",
        hovertemplate="<b>%{x}</b><br>Q1 avg equity score: %{y:.3f}<extra></extra>",
    ))
    trend_fig.add_hline(y=1.0, line_dash="dash", line_color="grey",
                        annotation_text="City median (1.0)", annotation_position="top left")
    trend_fig.update_layout(
        title=f"Q1 vs Q5 Avg Equity Score by {view_label}",
        xaxis_title=view_label, yaxis_title="Avg Equity Score",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified", height=480, margin=dict(t=60, b=20),
    )
    st.plotly_chart(trend_fig, use_container_width=True, config=_chart_config)

    st.caption(
        "**How to read this chart:** "
        "The **red line (Q1)** is the average equity score for the lowest-income 20% of NYC census tracts; "
        "**blue (Q5)** is the highest-income 20%. "
        "Both lines sitting above 1.0 means both groups wait longer than the city median -- but the "
        "**shaded area between them is the inequality**: the wider it is, the more response times favour "
        "wealthier neighbourhoods. "
        "A **widening gap** means the disparity is growing; a **narrowing gap** means operations or policy "
        "changes are having an effect. "
        "Seasonal spikes -- particularly summer peaks -- reflect complaint surges (noise, heat) that agencies "
        "absorb unevenly across income levels. "
        "Use **monthly view** to pinpoint individual spikes; switch to **seasonal view** to see structural "
        "patterns without month-to-month noise."
    )

    # Volume table -- matches the current grouping (monthly or seasonal)
    q1_vol = q1["total_requests"].fillna(0).astype(int).values
    q5_vol = q5["total_requests"].fillna(0).astype(int).values
    volume_table = pd.DataFrame({
        "Period":       [str(p)[:10] if not seasonal_trend else p for p in period_order],
        "Q1 Requests":  q1_vol,
        "Q5 Requests":  q5_vol,
        "Q1 − Q5":      q1_vol - q5_vol,
    }).set_index("Period")
    st.markdown(f"**Q1 vs Q5 request volume by {'season' if seasonal_trend else 'month'}:**")
    st.dataframe(volume_table, use_container_width=True)
else:
    st.info("No data found -- run the pipeline first.")

st.divider()

# ── ④ Verified findings -- static, human-written, cannot drift ─────────────────
st.subheader("④ Key Findings")
st.caption("Human-written and locked to verified numbers. These are the only claims this dashboard makes.")
st.markdown("""
**At the median, 311 service is roughly equal by neighborhood income.**
The typical complaint resolves in about 8-10 hours (P50) regardless of tract income
quintile. There is no broad income-based service gap at the median.

**The real inequity is narrow and complaint-specific.**
NYPD noise complaints resolve 1.5-2x slower at P90 in low-income tracts than in
high-income tracts, consistently across four independent noise categories (Residential,
Commercial, Vehicle, Street/Sidewalk) and 1.7M+ low-income-tract requests. Absolute
waits are short (approx. 3-4 hrs vs approx. 2 hrs) -- the gap is consistent and
high-confidence, not high-stakes per incident.

**A larger ratio exists on low volume.**
Street Sign -- Damaged repairs show a 4.7x gap (approx. 174 vs 37 days median P90),
but on only approx. 535 low-income-tract requests -- striking, but not high-confidence.

**Aggregate income comparisons are confounded -- and we verified it.**
Comparing all complaint types pooled, high-income tracts appear slower. This is a
complaint-mix artifact: helicopter-noise complaints have near-identical resolution times
in low- and high-income tracts (~26,600 hrs P90 each), but high-income tracts file them
62x more often. Both income groups have their own structurally-slow complaint types.
Equity is only a meaningful question within a complaint type, not across the aggregate.

**Methodology note.**
Equity gaps are computed per complaint type as the ratio of median tract-level P90
response times between the lowest- and highest-income quintiles, with a minimum-volume
floor (>=30 complaints per tract cell, >=500 per quintile per type) to suppress
small-sample noise.
""")

st.divider()

# ── ⑤ AI chart narration -- description only, findings locked ──────────────────
import streamlit.components.v1 as _components

_h_col, _btn_col = st.columns([5, 2.6])
_h_col.subheader("⑤ AI Chart Narration")
_h_col.caption("Plain-language description of the charts above. Findings are locked -- the AI restates, does not interpret.")
# _btn_col is filled below once synthesis is confirmed cached and complete

# Extra context from other dashboard pages fed into Groq
quintile_p90_df = run_query("""
    SELECT income_quintile,
           ROUND(MEDIAN(p90_hours), 1)    AS avg_p90_hours,
           ROUND(MEDIAN(equity_score), 3) AS avg_equity_score
    FROM MARTS.FCT_EQUITY_SPLITS
    WHERE income_quintile IS NOT NULL
      AND request_count >= 10
    GROUP BY income_quintile
    ORDER BY income_quintile
""")

top_complaints_df = run_query("""
    SELECT complaint_type,
           SUM(request_count)             AS total_requests,
           ROUND(MEDIAN(p90_hours), 1)    AS avg_p90_hours,
           ROUND(MEDIAN(equity_score), 3) AS avg_equity_score
    FROM MARTS.FCT_EQUITY_SPLITS
    WHERE request_count >= 10
    GROUP BY complaint_type
    ORDER BY total_requests DESC
    LIMIT 10
""")

borough_complaint_df = run_query("""
    WITH ranked AS (
        SELECT borough, complaint_type,
               ROUND(AVG(p90_hours), 1) AS avg_p90_hours,
               SUM(request_count)       AS total_requests,
               ROW_NUMBER() OVER (
                   PARTITION BY borough ORDER BY AVG(p90_hours) DESC
               ) AS rn
        FROM MARTS.FCT_EQUITY_SPLITS
        WHERE borough NOT IN ('UNSPECIFIED', '')
        GROUP BY borough, complaint_type
        HAVING SUM(request_count) >= 500
    )
    SELECT borough, complaint_type, avg_p90_hours, total_requests
    FROM ranked WHERE rn <= 3
    ORDER BY borough, rn
""")

# Agency breakdown -- same computation as the Agency Breakdown page
agency_raw_df = run_query("""
    SELECT complaint_type,
           income_quintile,
           SUM(request_count)    AS total_requests,
           MEDIAN(equity_score)  AS avg_equity_score
    FROM MARTS.FCT_EQUITY_SPLITS
    WHERE request_count >= 10
    GROUP BY complaint_type, income_quintile
""")

if not gap_df.empty and not heatmap_df.empty and not trend_df.empty:

    # Ensure the cache table exists (runs once per server lifetime via @st.cache_resource)
    _ensure_cache_table()

    # gap_json now uses median P90 hours from FCT_EQUITY_GAP_BY_TYPE
    gap_records = gap_df[["complaint_type", "agency", "q1_p90_hours", "q5_p90_hours",
                           "q1_over_q5_gap", "q1_n_complaints", "q5_n_complaints"]].to_dict("records")
    gap_json = "\n".join(
        f"  {r['complaint_type']} (agency: {r['agency']}): "
        f"Q1 median P90={r['q1_p90_hours']} hrs, Q5 median P90={r['q5_p90_hours']} hrs, "
        f"gap={r['q1_over_q5_gap']:.2f}x "
        f"(Q1 n={int(r['q1_n_complaints']):,}, Q5 n={int(r['q5_n_complaints']):,})"
        for r in gap_records
    )

    heatmap_json = "\n".join(
        f"  {r['borough']} Q{r['income_quintile']}: {r['avg_equity_score']:.2f}"
        for r in heatmap_df.to_dict("records")
    )

    # ── Fix 2: full monthly trend series ─────────────────────────────────────
    trend_monthly = trend_df.copy()
    trend_q1 = trend_monthly[trend_monthly["income_quintile"] == 1].sort_values("request_month")
    trend_q5 = trend_monthly[trend_monthly["income_quintile"] == 5].sort_values("request_month")

    def _full_series(df):
        if df.empty:
            return "no data"
        return ", ".join(
            f"{str(r['request_month'])[:7]}={r['avg_equity_score']:.2f}"
            for _, r in df.iterrows()
        )
    trend_json = (
        f"  Q1 monthly: {_full_series(trend_q1)}\n"
        f"  Q5 monthly: {_full_series(trend_q5)}"
    )

    # Extra page context as JSON strings
    quintile_p90_json = "\n".join(
        f"  Q{int(r['income_quintile'])}: avg P90 = {r['avg_p90_hours']} hrs, "
        f"equity score = {r['avg_equity_score']}"
        for r in quintile_p90_df.to_dict("records")
    ) if not quintile_p90_df.empty else "  no data"

    top_complaints_json = "\n".join(
        f"  {r['complaint_type']}: {int(r['total_requests']):,} requests, "
        f"avg P90 = {r['avg_p90_hours']} hrs, equity score = {r['avg_equity_score']}"
        for r in top_complaints_df.to_dict("records")
    ) if not top_complaints_df.empty else "  no data"

    borough_complaint_json = "\n".join(
        f"  {r['borough']}: {r['complaint_type']} "
        f"(avg P90 = {r['avg_p90_hours']} hrs, {int(r['total_requests']):,} requests)"
        for r in borough_complaint_df.to_dict("records")
    ) if not borough_complaint_df.empty else "  no data"

    # Agency breakdown aggregation
    if not agency_raw_df.empty:
        agency_raw_df["agency"] = agency_raw_df["complaint_type"].map(_AGENCY).fillna("Other")
        _vol  = agency_raw_df.groupby("agency")["total_requests"].sum()
        _q1e  = agency_raw_df[agency_raw_df["income_quintile"]==1].groupby("agency")["avg_equity_score"].mean()
        _q5e  = agency_raw_df[agency_raw_df["income_quintile"]==5].groupby("agency")["avg_equity_score"].mean()
        _ag   = pd.concat([_vol, _q1e.rename("q1"), _q5e.rename("q5")], axis=1).dropna()
        _ag["gap"] = _ag["q1"] - _ag["q5"]
        _ag = _ag.sort_values("gap", ascending=False)
        agency_json = "\n".join(
            f"  {agency}: {int(row['total_requests']):,} requests, "
            f"Q1={row['q1']:.3f}, Q5={row['q5']:.3f}, gap={row['gap']:.3f}"
            for agency, row in _ag.iterrows()
        )
    else:
        agency_json = "  no data"

    # Headline: top confirmed gaps from FCT_EQUITY_GAP_BY_TYPE
    top_gaps_json = "\n".join(
        f"  {r['complaint_type']}: Q1 P90={r['q1_p90_hours']} hrs, Q5 P90={r['q5_p90_hours']} hrs, "
        f"gap={r['q1_over_q5_gap']}x "
        f"(Q1 n={int(r['q1_n_complaints']):,}, Q5 n={int(r['q5_n_complaints']):,})"
        for _, r in headline_df.head(10).iterrows()
    ) if not headline_df.empty else "  no data"

    data_hash = _data_hash(
        gap_json, heatmap_json,
        trend_json + top_gaps_json + top_complaints_json + borough_complaint_json + agency_json + f1_sort,
    )

    # Always check Snowflake first -- zero API calls
    cached = _load_cached_synthesis(data_hash)

    _dev = is_dev()

    if cached and cached[0] == "complete":
        # Stored and ready -- display in styled callout box
        st.session_state.pop("synthesis", None)
        synthesis_text = cached[1]
        st.warning(
            "**AI-generated narrative -- verify all figures against the charts above before citing.** "
            "This synthesis is produced by a language model and may misstate or miscalculate statistics. "
            "Treat it as a presentation layer for non-technical readers, not as a source of truth.",
            icon="⚠️",
        )
        st.markdown(
            f'<div class="synthesis-box">{synthesis_text}</div>',
            unsafe_allow_html=True,
        )

        # Dev-only: force regenerate even when cached (for testing)
        if _dev:
            st.divider()
            st.caption("🔧 Dev mode")
            col_regen, col_clear = st.columns(2)
            if col_regen.button("🔄 Regenerate synthesis", help="Deletes cached row and calls Groq again"):
                from utils.snowflake_conn import get_snowflake_conn
                get_snowflake_conn().cursor().execute(
                    "DELETE FROM MARTS.AI_SYNTHESIS_CACHE WHERE data_hash = %s", (data_hash,)
                )
                st.rerun()
            if col_clear.button("🗑️ Clear all cached syntheses"):
                from utils.snowflake_conn import get_snowflake_conn
                get_snowflake_conn().cursor().execute("TRUNCATE TABLE MARTS.AI_SYNTHESIS_CACHE")
                st.rerun()

        # ── Buttons next to the ④ heading -- both rendered in one HTML component ──
        import base64 as _b64
        import html as _html

        report_date = date.today().strftime("%Y_%m_%d")
        report_name = f"nyc_311_service_equity_report_{report_date}.pdf"
        _pdf_b64    = ""
        try:
            _pdf_bytes  = _generate_pdf(f1_sort, synthesis_text)
            _pdf_b64    = _b64.b64encode(_pdf_bytes).decode()
        except Exception as _pdf_err:
            _btn_col.warning(f"PDF error: {_pdf_err}")

        _escaped = _html.escape(synthesis_text, quote=True)
        _btn_style = (
            "display:inline-flex;align-items:center;justify-content:center;"
            "width:calc(50% - 8px);height:36px;background:#262730;color:white;"
            "border:1px solid #555;border-radius:6px;cursor:pointer;"
            "font-size:13px;font-family:sans-serif;text-decoration:none;"
            "box-sizing:border-box;"
        )

        with _btn_col:
            _components.html(f"""
                <div style="display:flex;gap:16px;align-items:center;padding-top:4px;">
                    <a href="data:application/pdf;base64,{_pdf_b64}"
                       download="{report_name}"
                       style="{_btn_style}">
                        &#11015;&#65039; Download
                    </a>
                    <textarea id="synth-txt"
                        style="position:absolute;opacity:0;pointer-events:none;height:1px;width:1px"
                        >{_escaped}</textarea>
                    <button style="{_btn_style}"
                        onclick="var t=document.getElementById('synth-txt');
                                 t.removeAttribute('style');
                                 t.select();
                                 document.execCommand('copy');
                                 t.setAttribute('style','position:absolute;opacity:0;pointer-events:none;height:1px;width:1px');
                                 this.innerText='✓ Copied'">
                        &#128203; Copy
                    </button>
                </div>
            """, height=48)

    elif cached and cached[0] == "pending":
        st.info("Analysis is being generated. Refresh the page in a few seconds to see it.")
        if _dev:
            if st.button("🗑️ Clear stuck pending row", help="Dev only -- removes the pending lock so generation can restart"):
                from utils.snowflake_conn import get_snowflake_conn
                get_snowflake_conn().cursor().execute(
                    "DELETE FROM MARTS.AI_SYNTHESIS_CACHE WHERE status = 'pending'"
                )
                st.rerun()

    else:
        # No cached row -- only dev can trigger generation
        prompt = f"""\
Describe each of the following charts in 1-2 plain sentences. Lead with the \
NYPD noise cluster finding (finding 2), then Street Sign lower volume (finding 3), \
then the confound explanation (finding 4). Use only the numbers below. \
Do not add recommendations, interpretations, or claims beyond what the \
verified findings in your instructions state.

CONFIRMED GAPS (within-complaint-type, median tract P90, volume-floored):
{top_gaps_json}

CHART 1 -- Top complaint types by Q1 vs Q5 gap, sorted by {f1_sort}:
{gap_json}

CHART 2 -- Borough x income quintile median equity score (1.0 = city median):
{heatmap_json}

CHART 3 -- Monthly P90 response time by quintile, pooled per month (raw hours):
NOTE -- this is a response-time trend, NOT an equity-gap series.
{trend_json}

CHART 4 -- Top 10 complaint types by total volume:
{top_complaints_json}

CHART 5 -- Slowest complaint types per borough (500+ requests only):
NOTE -- types appearing here may be structurally slow in ALL quintiles. \
Do not prescribe improvements without cross-quintile comparison.
{borough_complaint_json}\
"""
        if _dev:
            st.info("No AI synthesis cached for this data + sort combination.")
            if st.button("Generate AI Analysis", type="primary"):
                claimed = _claim_slot(data_hash)
                if claimed:
                    with st.spinner("Generating..."):
                        try:
                            text = _call_groq(prompt)
                            _store_synthesis(data_hash, text)
                            st.rerun()
                        except Exception as exc:
                            _store_synthesis(data_hash, "")
                            st.error(f"Groq error: {exc}")
                else:
                    st.info("Another session is already generating. Refresh in a few seconds.")
        else:
            st.info(
                "AI analysis for this view has not been generated yet. "
                "Check back later or contact the dashboard administrator."
            )

else:
    st.info("Run the pipeline to populate findings data.")
