import plotly.graph_objects as go
import streamlit as st

from utils.snowflake_conn import run_query
from utils.styles import inject_css

inject_css()

st.header("Equity Gap Timeline — Q1 vs Q5")
st.markdown("""
Tracks whether the response-time disparity between the **lowest-income (Q1)** and
**highest-income (Q5)** census tracts is growing or closing over time.
""")

# ── View toggle ───────────────────────────────────────────────────────────────
seasonal = st.checkbox(
    "View by season instead of month",
    value=False,
    help="Collapses monthly data into Spring / Summer / Fall / Winter averages "
         "so structural trends stand out from month-to-month noise.",
)

# ── Query ─────────────────────────────────────────────────────────────────────
if not seasonal:
    sql = """
    SELECT
        request_month,
        income_quintile,
        AVG(equity_score) AS avg_equity_score
    FROM MARTS.FCT_EQUITY_SPLITS
    WHERE income_quintile IN (1, 5)
    GROUP BY request_month, income_quintile
    ORDER BY request_month
    """
else:
    sql = """
    SELECT
        YEAR(request_month)  AS yr,
        CASE
            WHEN MONTH(request_month) IN (3,4,5)   THEN 'Spring'
            WHEN MONTH(request_month) IN (6,7,8)   THEN 'Summer'
            WHEN MONTH(request_month) IN (9,10,11) THEN 'Fall'
            ELSE 'Winter'
        END AS season,
        CASE
            WHEN MONTH(request_month) IN (3,4,5)   THEN 2
            WHEN MONTH(request_month) IN (6,7,8)   THEN 3
            WHEN MONTH(request_month) IN (9,10,11) THEN 4
            ELSE 1
        END AS season_order,
        income_quintile,
        AVG(equity_score) AS avg_equity_score
    FROM MARTS.FCT_EQUITY_SPLITS
    WHERE income_quintile IN (1, 5)
    GROUP BY yr, season, season_order, income_quintile
    ORDER BY yr, season_order
    """

df = run_query(sql)

if df.empty:
    st.info("No data found — run the pipeline first.")
    st.stop()

# ── Build x-axis labels ───────────────────────────────────────────────────────
if seasonal:
    df["period"] = df["yr"].astype(str) + " " + df["season"]
    # Preserve chronological order already returned by SQL
    period_order = df[["yr", "season_order", "period"]].drop_duplicates() \
                     .sort_values(["yr", "season_order"])["period"].tolist()
else:
    df["period"] = df["request_month"]
    period_order = sorted(df["period"].unique())

q1 = df[df["income_quintile"] == 1].set_index("period").reindex(period_order).reset_index()
q5 = df[df["income_quintile"] == 5].set_index("period").reindex(period_order).reset_index()

# ── Chart ─────────────────────────────────────────────────────────────────────
fig = go.Figure()

# Q5 drawn first — fill='tonexty' on Q1 shades the gap between the two lines
fig.add_trace(go.Scatter(
    x=q5["period"],
    y=q5["avg_equity_score"],
    name="Q5 — highest income",
    mode="lines+markers",
    line=dict(color="#4C9BE8", width=2),
    marker=dict(size=5),
    hovertemplate="<b>%{x}</b><br>Q5 avg equity score: %{y:.3f}<extra></extra>",
))

fig.add_trace(go.Scatter(
    x=q1["period"],
    y=q1["avg_equity_score"],
    name="Q1 — lowest income",
    mode="lines+markers",
    line=dict(color="#E84C4C", width=2),
    marker=dict(size=5),
    fill="tonexty",
    fillcolor="rgba(232, 76, 76, 0.12)",
    hovertemplate="<b>%{x}</b><br>Q1 avg equity score: %{y:.3f}<extra></extra>",
))

fig.add_hline(
    y=1.0,
    line_dash="dash",
    line_color="grey",
    annotation_text="City median (1.0)",
    annotation_position="top left",
)

view_label = "Season" if seasonal else "Month"
fig.update_layout(
    title=f"Q1 vs Q5 Avg Equity Score by {view_label}",
    xaxis_title=view_label,
    yaxis_title="Avg Equity Score",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    hovermode="x unified",
    height=480,
    margin=dict(t=60, b=20),
)

st.plotly_chart(fig, use_container_width=True)

# ── Caption ───────────────────────────────────────────────────────────────────
st.caption(
    "**How to read this chart:** "
    "The **red line (Q1)** is the average equity score for the lowest-income 20% of NYC census tracts; "
    "**blue (Q5)** is the highest-income 20%. "
    "Both lines sitting above 1.0 means both groups wait longer than the city median — but the "
    "**shaded area between them is the inequality**: the wider it is, the more response times favour "
    "wealthier neighbourhoods. "
    "A **widening gap** means the disparity is growing; a **narrowing gap** means operations or policy "
    "changes are having an effect. "
    "Seasonal spikes — particularly summer peaks — reflect complaint surges (noise, heat) that agencies "
    "absorb unevenly across income levels. "
    "Use **monthly view** to pinpoint individual spikes; switch to **seasonal view** to see structural "
    "patterns without month-to-month noise."
)
