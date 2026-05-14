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

sql = """
SELECT
    borough,
    complaint_type,
    AVG(p50_hours)          AS p50_hours,
    AVG(p90_hours)          AS p90_hours,
    SUM(request_count)      AS complaint_count,
    AVG(equity_score)       AS avg_equity_score
FROM MARTS.FCT_EQUITY_SPLITS
GROUP BY borough, complaint_type
"""
df = run_query(sql)

if df.empty:
    st.warning("No data available.")
    st.stop()

metric = st.radio(
    "Color heatmap by",
    options=["p90_hours", "p50_hours", "complaint_count"],
    horizontal=True,
)

# Show all complaint types — height scales automatically in chart_helpers
st.plotly_chart(
    complaint_heatmap(df, metric),
    use_container_width=True,
)

_metric_explanations = {
    "p90_hours": (
        "🔴 **Red = longer resolution time** in that borough for this complaint type. "
        "A dark red cell means the worst-served 10% of residents waited a very long time — "
        "a genuine service problem worth investigating. "
        "🟢 **Green = resolves quickly.**"
    ),
    "p50_hours": (
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
st.caption(_metric_explanations[metric])

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
    "Bar color = average equity score across all tracts for that complaint type. "
    "🔴 **Red = equity score well above 1.0** — lower-income tracts wait significantly longer "
    "than the typical NYC neighborhood for this type, pointing to an agency response disparity. "
    "🟢 **Green = equity score near 1.0** — service is distributed relatively evenly across "
    "neighborhoods regardless of income. "
    "High-volume bars that are red are the highest-priority equity issues — "
    "they affect the most residents and the service gap is the largest."
)
