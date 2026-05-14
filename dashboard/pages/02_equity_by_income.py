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

    **How equity score is calculated:**
    Equity score = this tract's P90 ÷ the **median tract P90** citywide for that complaint type.
    Every tract counts equally in the baseline regardless of complaint volume — high-volume
    boroughs do not skew the reference point. A score of 1.0 means this tract matches
    the *typical NYC neighborhood experience*.

    **Bar chart — Avg Equity Score by Income Quintile:**
    - Each bar is one income quintile (1–5)
    - Bar height = average equity score across all tracts in that quintile
    - The dashed line at `1.0` = median tract baseline. Bars above it mean that quintile
      waits longer than the typical NYC neighborhood for this complaint type
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
st.caption(
    "**Avg equity score** = the mean of all tract equity scores within that income quintile. "
    "Each tract's equity score is its own P90 divided by the median tract P90 citywide — "
    "so averaging them across a quintile gives a single number representing how that income group "
    "performs relative to the typical NYC neighborhood. "
    "A score of 1.0 means the quintile matches the median tract. Above 1.0 means slower. Below 1.0 means faster."
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
st.caption(
    f"Each dot is one census tract's median income vs its P90 response time for **{selected_complaint}**. "
    "A downward slope (higher income → lower P90) confirms an income-driven equity gap for this complaint type and its responsible agency. "
    "A flat line means income has little effect — geography or other factors may explain the variance. "
    "Wide vertical spread at any income level means high inconsistency within that income band."
)
st.info(
    "💡 **Filter by borough:** Click a borough name in the legend to hide it. "
    "Double-click a borough name to isolate it and hide all others. "
    "Click again to restore."
)

st.caption(
    "Income quintile 1 = lowest income, 5 = highest. "
    "Equity score = tract P90 ÷ median tract P90 citywide (equal weight per tract). "
    "Score > 1.0 means this tract waits longer than the typical NYC neighborhood."
)
