import streamlit as st

from utils.snowflake_conn import run_query
from utils.chart_helpers import equity_bar, scatter_income_vs_wait
from utils.styles import inject_css

inject_css()

st.header("Equity Score by Income Quintile")

with st.expander("How to read this page"):
    st.markdown("""
    **What you're looking at:**
    This page answers whether lower-income neighborhoods systematically receive slower 311 service
    than higher-income ones — for a specific complaint type.

    **Income quintiles:**
    NYC's ~2,168 census tracts are divided into 5 equal groups by median household income:
    - **Quintile 1** = lowest income (bottom 20% of tracts)
    - **Quintile 5** = highest income (top 20% of tracts)

    **The three metric callouts at the top:**
    - **Bottom quintile avg P90** — average 90th percentile wait time in the poorest tracts
    - **Top quintile avg P90** — average 90th percentile wait time in the wealthiest tracts
    - **Equity ratio** — bottom ÷ top. A ratio of `2.0×` means the poorest neighborhoods
      wait twice as long as the wealthiest for the same type of complaint

    **Bar chart — Avg Equity Score by Income Quintile:**
    - Each bar is one income quintile (1–5)
    - Bar height = average equity score across all tracts in that quintile
    - The dashed grey line at `1.0` = city average. Bars above it mean that quintile waits longer than average
    - A clear upward slope from quintile 5 → 1 confirms a systematic equity gap

    **Scatter plot — Income vs P90 Response Time:**
    - Each dot is one census tract
    - X axis = median household income of the tract
    - Y axis = P90 response time in hours
    - Color = borough — **click a borough in the legend to show/hide it; double-click to isolate**
    - Size = number of complaints in that tract
    - A downward slope (higher income → lower wait time) confirms the equity pattern
    - Outlier dots far above the trend are tracts with unusually slow service worth investigating

    **Tip:** Switch complaint types to compare categories — rodent complaints and heat/hot water
    often show stronger equity gaps than noise complaints.
    """)

COMPLAINT_QUERY = "SELECT DISTINCT complaint_type FROM MARTS.FCT_EQUITY_SPLITS ORDER BY 1"
complaint_types = run_query(COMPLAINT_QUERY)["complaint_type"].tolist()
selected_complaint = st.selectbox("Complaint type", complaint_types, index=0)

quintile_sql = f"""
SELECT
    income_quintile,
    AVG(equity_score)           AS avg_equity_score,
    AVG(p90_hours)              AS avg_p90_hours,
    SUM(request_count)          AS total_complaints
FROM MARTS.FCT_EQUITY_SPLITS
WHERE complaint_type = '{selected_complaint}'
GROUP BY income_quintile
ORDER BY income_quintile
"""
quintile_df = run_query(quintile_sql)

if quintile_df.empty:
    st.warning("No data for this selection.")
    st.stop()

bottom = quintile_df[quintile_df["income_quintile"] == 1]["avg_p90_hours"].values
top = quintile_df[quintile_df["income_quintile"] == 5]["avg_p90_hours"].values
if bottom.size and top.size and top[0]:
    col1, col2, col3 = st.columns(3)
    col1.metric("Bottom quintile avg P90 (hrs)", f"{bottom[0]:.1f}")
    col2.metric("Top quintile avg P90 (hrs)", f"{top[0]:.1f}")
    col3.metric("Equity ratio (bottom / top)", f"{bottom[0] / top[0]:.2f}×")

st.plotly_chart(
    equity_bar(
        quintile_df,
        x="income_quintile",
        y="avg_equity_score",
        title=f"Avg Equity Score by Income Quintile — {selected_complaint}",
    ),
    use_container_width=True,
)

scatter_sql = f"""
SELECT
    tract_geoid,
    complaint_type,
    borough,
    MAX(median_household_income) AS median_household_income,
    AVG(p90_hours)               AS p90_hours,
    AVG(equity_score)            AS equity_score,
    SUM(request_count)           AS complaint_count
FROM MARTS.FCT_EQUITY_SPLITS
WHERE complaint_type = '{selected_complaint}'
  AND p90_hours IS NOT NULL
GROUP BY tract_geoid, complaint_type, borough
"""
scatter_df = run_query(scatter_sql)
st.plotly_chart(scatter_income_vs_wait(scatter_df), use_container_width=True)
st.info(
    "💡 **Filter by borough:** Click a borough name in the legend to hide it. "
    "Double-click a borough name to isolate it and hide all others. "
    "Click again to restore."
)

st.caption(
    "Income quintile 1 = lowest income, 5 = highest. "
    "Equity score > 1.0 means the tract waits longer than the city average for that complaint type."
)
