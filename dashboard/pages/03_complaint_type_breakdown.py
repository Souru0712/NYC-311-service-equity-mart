import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotly.express as px
import streamlit as st

from utils.snowflake_conn import run_query
from utils.chart_helpers import complaint_heatmap
from utils.styles import inject_css

inject_css()

st.header("Complaint Type Breakdown by Borough")

with st.expander("How to read this page"):
    st.markdown("""
    **What you're looking at:**
    This page shows how all 311 complaint types distribute across NYC's five boroughs — and how
    response times and equity vary by category and location.

    **Heatmap — All Complaint Types × Borough:**
    - Rows = every complaint type in the dataset (scroll down to see all)
    - Columns = the 5 NYC boroughs
    - Cell color = the selected metric for that complaint type in that borough
    - Toggle the metric using the radio buttons above the chart:
        - **p90_hours** — 90th percentile response time (worst-case experience)
        - **p50_hours** — median response time (typical experience)
        - **complaint_count** — total number of complaints
    - Darker red = higher value. A dark cell means that category takes particularly long
      (or has high volume) in that borough
    - Comparing a row across boroughs reveals whether a complaint type is handled
      consistently or has geographic disparities

    **Bar chart — Top 10 Complaint Types by Volume:**
    - Sorted by total complaint count (longest bar = most complaints citywide)
    - Bar color = average equity score for that complaint type across all tracts
        - 🟢 Green = equity score near 1.0 (service matches the typical NYC neighborhood)
        - 🔴 Red = equity score well above 1.0 (tracts wait significantly longer than typical)
    - High-volume complaint types with red bars are the highest-priority equity issues —
      they affect many residents and the service gap is large
    - Equity score = tract P90 ÷ **median tract P90** citywide (equal weight per tract,
      not skewed by complaint volume in any single borough)

    **Tip:** Switch to `complaint_count` to identify the highest-volume categories per borough,
    then switch to `p90_hours` to see which ones are the slowest to resolve.
    """)

# ── Date range filter ─────────────────────────────────────────────────────────
_DEFAULT_START = "2020-01-01"
_DEFAULT_END   = date.today().strftime("%Y-%m-%d")
_DATE_RE       = re.compile(r"^\d{4}-\d{2}-\d{2}$")

st.caption("📅 Date range · Format: YYYY-MM-DD · e.g. 2023-01-01")
_dc1, _dc2, _dc3 = st.columns([2, 2, 1])
_start_input = _dc1.text_input("Start date", value=_DEFAULT_START, key="cb_start")
_end_input   = _dc2.text_input("End date",   value=_DEFAULT_END,   key="cb_end")
if _dc3.button("↺ Reset", key="cb_reset", use_container_width=True):
    st.session_state.pop("cb_start", None)
    st.session_state.pop("cb_end",   None)
    st.rerun()

start_date  = _start_input if _DATE_RE.match(_start_input or "") else _DEFAULT_START
end_date    = _end_input   if _DATE_RE.match(_end_input   or "") else _DEFAULT_END

sql = f"""
SELECT
    borough,
    complaint_type,
    AVG(p50_hours)          AS p50_hours,
    AVG(p90_hours)          AS p90_hours,
    SUM(request_count)      AS complaint_count,
    AVG(equity_score)       AS avg_equity_score
FROM MARTS.FCT_EQUITY_SPLITS
WHERE request_month BETWEEN '{start_date}' AND '{end_date}'
GROUP BY borough, complaint_type
"""
df = run_query(sql)

if df.empty:
    st.warning("No data available.")
    st.stop()

_metric_map = {"p90": "p90_hours", "p50": "p50_hours", "complaint_count": "complaint_count"}
metric_label = st.radio(
    "Color heatmap by",
    options=list(_metric_map.keys()),
    horizontal=True,
)
metric = _metric_map[metric_label]

# Show all complaint types — height scales automatically in chart_helpers
st.plotly_chart(
    complaint_heatmap(df, metric),
    use_container_width=True,
)

_metric_explanations = {
    "p90": (
        "🔴 **Red = longer resolution time** in that borough for this complaint type. "
        "A dark red cell means the worst-served 10% of residents waited a very long time — "
        "a genuine service problem worth investigating. "
        "🟢 **Green = resolves quickly.**"
    ),
    "p50": (
        "🔴 **Red = longer median resolution time** — the *typical* resident in that borough "
        "waited a long time for this complaint type to be resolved. "
        "🟢 **Green = typical resident resolved quickly.**"
    ),
    "complaint_count": (
        "🔴 **Red = high complaint volume** filed in that borough for this type. "
        "This reflects demand, not service quality — a red cell here does not mean slow service, "
        "it may simply reflect population density or a known local issue. "
        "🟢 **Green = fewer complaints filed.**"
    ),
}
st.caption(_metric_explanations[metric_label])

top10 = (
    df.groupby("complaint_type")
    .agg(total_complaints=("complaint_count", "sum"), avg_equity=("avg_equity_score", "mean"))
    .nlargest(10, "total_complaints")
    .reset_index()
)
fig = px.bar(
    top10.sort_values("total_complaints"),
    x="total_complaints",
    y="complaint_type",
    color="avg_equity",
    color_continuous_scale="RdYlGn_r",
    orientation="h",
    title="Top 10 Complaint Types by Volume (color = avg equity score)",
    labels={"total_complaints": "Total Complaints", "avg_equity": "Avg Equity Score"},
)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Bar length = total complaints filed citywide. "
    "Bar color = average equity score across **all tracts** for that complaint type — "
    "this is city-wide, not broken down by income. "
    "🔴 **Red = high average equity score** — this complaint type has long resolution times "
    "across the entire city, meaning the responsible agency is not resolving it efficiently "
    "regardless of neighborhood. It is an agency performance issue. "
    "🟢 **Green = average equity score near 1.0** — the agency resolves this type consistently "
    "and quickly across NYC. "
    "A high-volume red bar is the most urgent signal: the agency is struggling to keep up "
    "with a complaint type that affects a large number of residents citywide."
)
