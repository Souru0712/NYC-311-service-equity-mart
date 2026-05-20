from groq import Groq
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.snowflake_conn import run_query
from utils.styles import inject_css

inject_css()

# ── Claude synthesis ──────────────────────────────────────────────────────────
_SYNTHESIS_SYSTEM = """\
You are a data analyst specialising in NYC municipal service equity.
You will receive three findings from a 311 response-time dashboard and must produce:

1. A root-cause assessment (3–5 sentences) that directly answers: is the disparity
   driven by income, geography (borough), or agency response protocols — or some
   combination? Use the data to justify your answer. Name specific agencies, boroughs,
   and complaint types where the numbers support it.

2. Three to four concrete, actionable recommendations. Each recommendation must be
   tied explicitly to one of the three findings. Name the agency or office responsible
   for each action.

Format your response as markdown with two sections:
**Root Cause Assessment**
**Recommended Actions**

Write for a general public audience. Be direct. Do not hedge unless the data is
genuinely ambiguous. Do not summarise what the findings show — assess and recommend.\
"""


def _data_hash(gap_json: str, heatmap_json: str, trend_json: str) -> str:
    import hashlib
    return hashlib.md5((gap_json + heatmap_json + trend_json).encode()).hexdigest()


def _ensure_cache_table() -> None:
    """Ensure AI_SYNTHESIS_CACHE exists. Idempotent — safe to call on every page load."""
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

    status: 'pending' — another process is generating, don't call Groq again.
            'complete' — ready to display.
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
        max_tokens=1024,
    )
    return response.choices[0].message.content

# Agency responsible for each complaint type — mirrors the reference tab in app.py
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
The other pages show *what* is happening. This page answers *why* — and *who* should act on it.

The core question: when low-income neighborhoods wait longer for 311 responses, is it because of
**where they are** (geography), **how much they earn** (income), or **what they reported**
(complaint type / agency responsible)?
""")

with st.expander("How to read this page"):
    st.markdown("""
    **Equity score methodology:**
    Equity score = tract P90 ÷ **median tract P90** citywide for that complaint type and month.
    Every tract counts equally in the baseline — high-volume boroughs do not skew the reference.
    Score 1.0 = this tract matches the typical NYC neighborhood.
    Score > 1.0 = residents wait longer than the typical tract.

    **Finding 1 — Equity gap by complaint type:**
    Each bar is one complaint type, sized by how much longer Q1 (lowest income) tracts wait
    relative to Q5 (highest income) tracts on average equity score.
    The agency column tells you who is accountable.
    If the gap clusters around one or two agencies, the problem is agency-driven — not just
    neighborhood-driven.

    **Finding 2 — Borough × income quintile heatmap:**
    Each cell is the average equity score for that borough/quintile combination.
    Green (≤1.0) = at or below the median tract baseline. Red (>1.0) = longer than typical.
    - If all quintiles in a borough are red → the whole borough is underserved regardless of income
      (geographic problem).
    - If you see a green-to-red gradient from Q5 → Q1 within every borough → income is the
      predictor, not location (structural equity problem).
    - The most actionable pattern is a borough where Q1 is deeply red but Q5 is green —
      same city, same agency, different treatment.

""")

st.divider()

# ── Headline metrics ──────────────────────────────────────────────────────────
headline_sql = """
WITH quintile_avgs AS (
    SELECT
        AVG(CASE WHEN income_quintile = 1 THEN equity_score END) AS q1_avg,
        AVG(CASE WHEN income_quintile = 5 THEN equity_score END) AS q5_avg
    FROM MARTS.FCT_EQUITY_SPLITS
    WHERE income_quintile IN (1, 5)
)
SELECT
    ROUND(q1_avg, 3)                            AS q1_avg_equity,
    ROUND(q5_avg, 3)                            AS q5_avg_equity,
    ROUND(q1_avg / NULLIF(q5_avg, 0), 2)        AS overall_ratio
FROM quintile_avgs
"""
headline_df = run_query(headline_sql)

if not headline_df.empty:
    row = headline_df.iloc[0]
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Q1 avg equity score",
        f"{row['q1_avg_equity']:.2f}",
        help="Average equity score for the lowest-income 20% of tracts. 1.0 = city average wait.",
    )
    col2.metric(
        "Q5 avg equity score",
        f"{row['q5_avg_equity']:.2f}",
        help="Average equity score for the highest-income 20% of tracts.",
    )
    col3.metric(
        "Q1 / Q5 ratio",
        f"{row['overall_ratio']:.2f}×",
        help="How many times longer Q1 tracts wait relative to Q5, city-wide across all complaint types.",
    )

st.divider()

# ── Finding 1: Which complaint types drive the gap? ───────────────────────────
st.subheader("① Which complaint types have the biggest equity gap — and which agencies own them?")
st.markdown("""
The bars below show the top 10 complaint types ranked by the difference in average equity score
between Q1 and Q5 tracts. A larger gap means the city's response is *more unequal* for that
complaint type. The **Agency** column identifies who is accountable for closing it.
""")

min_volume_filter = st.checkbox(
    "Only show complaint types with 500+ total requests",
    value=True,
    help="Excludes low-volume types (e.g. Cranes & Derricks: 191 requests) whose equity gap "
         "is statistically unreliable and skews the chart.",
)
volume_clause = "AND total_requests >= 500" if min_volume_filter else ""

f1_sort = st.radio(
    "Order by",
    ["Gap desc", "Total requests desc", "Gap desc, then total requests desc"],
    horizontal=True,
    key="f1_sort",
)
f1_order = {
    "Gap desc":                              "equity_gap DESC",
    "Total requests desc":                   "total_requests DESC",
    "Gap desc, then total requests desc":    "equity_gap DESC, total_requests DESC",
}[f1_sort]

gap_sql = f"""
WITH gaps AS (
    SELECT
        complaint_type,
        AVG(CASE WHEN income_quintile = 1 THEN equity_score END) AS q1_avg,
        AVG(CASE WHEN income_quintile = 5 THEN equity_score END) AS q5_avg,
        SUM(request_count)                                        AS total_requests
    FROM MARTS.FCT_EQUITY_SPLITS
    WHERE income_quintile IN (1, 5)
    GROUP BY complaint_type
)
SELECT
    complaint_type,
    ROUND(q1_avg, 3)               AS q1_avg_equity,
    ROUND(q5_avg, 3)               AS q5_avg_equity,
    ROUND(q1_avg - q5_avg, 3)      AS equity_gap,
    total_requests
FROM gaps
WHERE q1_avg IS NOT NULL
  AND q5_avg IS NOT NULL
  {volume_clause}
ORDER BY {f1_order}
LIMIT 10
"""
gap_df = run_query(gap_sql)

if not gap_df.empty:
    gap_df["agency"] = gap_df["complaint_type"].map(_AGENCY).fillna("Various")

    fig = px.bar(
        gap_df.sort_values("equity_gap"),
        x="equity_gap",
        y="complaint_type",
        color="equity_gap",
        color_continuous_scale="RdYlGn_r",
        orientation="h",
        hover_data={"agency": True, "q1_avg_equity": True, "q5_avg_equity": True, "total_requests": True},
        labels={
            "equity_gap": "Equity gap (Q1 avg − Q5 avg equity score)",
            "complaint_type": "Complaint Type",
            "agency": "Agency",
            "q1_avg_equity": "Q1 avg equity score",
            "q5_avg_equity": "Q5 avg equity score",
            "total_requests": "Total requests",
        },
        title="Top 10 complaint types by equity gap (Q1 − Q5 avg equity score)",
    )
    fig.update_layout(coloraxis_showscale=False, yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Details for the above complaint types:**")
    st.table(
        gap_df[["complaint_type", "agency", "total_requests", "q1_avg_equity", "q5_avg_equity", "equity_gap"]]
        .rename(columns={
            "complaint_type": "Complaint Type",
            "agency": "Agency",
            "total_requests": "Total Requests",
            "q1_avg_equity": "Q1 Avg Equity",
            "q5_avg_equity": "Q5 Avg Equity",
            "equity_gap": "Gap (Q1−Q5)",
        })
        .set_index("Complaint Type")
    )
else:
    st.info("No data found — run the pipeline first.")

st.divider()

# ── Finding 2: Geography vs income ───────────────────────────────────────────
st.subheader("② Is the gap geographic or income-driven? Borough × income quintile")
st.markdown("""
Each cell shows the average equity score for that borough and income quintile.
**Green = at or below city-average wait. Red = above city-average wait.**

Read each borough row left to right (Q1 → Q5). A gradient from red to green within a single
borough row means income — not just location — determines how fast the city responds.
A borough where every cell is red regardless of quintile points to a resource deficit for that
entire area.
""")

heatmap_sql = """
SELECT
    borough,
    income_quintile,
    ROUND(AVG(equity_score), 3) AS avg_equity_score
FROM MARTS.FCT_EQUITY_SPLITS
WHERE borough NOT IN ('UNSPECIFIED', '')
  AND income_quintile IS NOT NULL
GROUP BY borough, income_quintile
ORDER BY borough, income_quintile
"""
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
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No data found — run the pipeline first.")

st.divider()

# ── Finding 3: Equity trend over time ────────────────────────────────────────
st.subheader("③ Is the gap growing or closing? Equity score trend — Q1 vs Q5")
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

# Always fetch monthly — used for the chart (monthly mode) and AI synthesis
trend_sql = """
SELECT
    request_month,
    income_quintile,
    AVG(equity_score)  AS avg_equity_score,
    SUM(request_count) AS total_requests
FROM MARTS.FCT_EQUITY_SPLITS
WHERE income_quintile IN (1, 5)
GROUP BY request_month, income_quintile
ORDER BY request_month
"""
trend_df = run_query(trend_sql)

if not trend_df.empty:
    import pandas as pd

    if seasonal_trend:
        # Aggregate monthly data to seasons in pandas — avoids a second SQL query
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
        name="Q5 — highest income", mode="lines+markers",
        line=dict(color="#4C9BE8", width=2), marker=dict(size=5),
        hovertemplate="<b>%{x}</b><br>Q5 avg equity score: %{y:.3f}<extra></extra>",
    ))
    trend_fig.add_trace(go.Scatter(
        x=q1["period"], y=q1["avg_equity_score"],
        name="Q1 — lowest income", mode="lines+markers",
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
    st.plotly_chart(trend_fig, use_container_width=True)

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

    # Volume table — matches the current grouping (monthly or seasonal)
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
    st.info("No data found — run the pipeline first.")

st.divider()

# ── AI synthesis ──────────────────────────────────────────────────────────────
st.subheader("④ What the data tells us — and what should happen next")
st.caption("AI-generated synthesis stored in Snowflake. Groq is called only once per data refresh.")

# Extra context from other dashboard pages fed into Groq
quintile_p90_df = run_query("""
    SELECT income_quintile,
           ROUND(AVG(p90_hours), 1)    AS avg_p90_hours,
           ROUND(AVG(equity_score), 3) AS avg_equity_score
    FROM MARTS.FCT_EQUITY_SPLITS
    WHERE income_quintile IS NOT NULL
    GROUP BY income_quintile
    ORDER BY income_quintile
""")

top_complaints_df = run_query("""
    SELECT complaint_type,
           SUM(request_count)          AS total_requests,
           ROUND(AVG(p90_hours), 1)    AS avg_p90_hours,
           ROUND(AVG(equity_score), 3) AS avg_equity_score
    FROM MARTS.FCT_EQUITY_SPLITS
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

# Agency breakdown — same computation as the Agency Breakdown page
agency_raw_df = run_query("""
    SELECT complaint_type,
           income_quintile,
           SUM(request_count) AS total_requests,
           AVG(equity_score)  AS avg_equity_score
    FROM MARTS.FCT_EQUITY_SPLITS
    GROUP BY complaint_type, income_quintile
""")

if not gap_df.empty and not heatmap_df.empty and not trend_df.empty and not headline_df.empty:

    # Ensure the cache table exists (runs once per server lifetime via @st.cache_resource)
    _ensure_cache_table()

    # Build compact text representations of the three findings
    gap_records = gap_df[["complaint_type", "agency", "q1_avg_equity", "q5_avg_equity", "equity_gap"]].to_dict("records")
    gap_json = "\n".join(
        f"  {r['complaint_type']} (agency: {r['agency']}): gap={r['equity_gap']:.3f}, "
        f"Q1={r['q1_avg_equity']:.2f}, Q5={r['q5_avg_equity']:.2f}"
        for r in gap_records
    )

    heatmap_json = "\n".join(
        f"  {r['borough']} Q{r['income_quintile']}: {r['avg_equity_score']:.2f}"
        for r in heatmap_df.to_dict("records")
    )

    # Always use monthly trend for AI synthesis regardless of display mode
    trend_monthly = trend_df.copy()
    trend_q1 = trend_monthly[trend_monthly["income_quintile"] == 1].sort_values("request_month")
    trend_q5 = trend_monthly[trend_monthly["income_quintile"] == 5].sort_values("request_month")
    def _trend_line(df, label):
        if df.empty:
            return f"  {label}: no data"
        first, last = df.iloc[0], df.iloc[-1]
        direction = "widening" if last["avg_equity_score"] > first["avg_equity_score"] else "narrowing"
        return (
            f"  {label}: {first['avg_equity_score']:.2f} ({str(first['request_month'])[:10]}) → "
            f"{last['avg_equity_score']:.2f} ({str(last['request_month'])[:10]}) — {direction}"
        )
    trend_json = "\n".join([_trend_line(trend_q1, "Q1"), _trend_line(trend_q5, "Q5")])

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

    row     = headline_df.iloc[0]
    q1_avg  = float(row["q1_avg_equity"])
    q5_avg  = float(row["q5_avg_equity"])
    ratio   = float(row["overall_ratio"])

    data_hash = _data_hash(
        gap_json, heatmap_json,
        trend_json + quintile_p90_json + top_complaints_json + borough_complaint_json + agency_json,
    )

    # Always check Snowflake first — zero API calls
    cached = _load_cached_synthesis(data_hash)

    if cached and cached[0] == "complete":
        # Stored and ready — display in styled callout box
        st.session_state.pop("synthesis", None)
        st.markdown(
            f'<div class="synthesis-box">{cached[1]}</div>',
            unsafe_allow_html=True,
        )

    elif cached and cached[0] == "pending":
        # Another user already clicked — don't call Groq again
        st.info("Analysis is being generated. Refresh the page in a few seconds to see it.")

    else:
        # No row yet — show the generate button
        prompt = f"""\
Overall equity gap:
  Q1 avg equity score: {q1_avg:.2f}
  Q5 avg equity score: {q5_avg:.2f}
  Q1/Q5 ratio: {ratio:.2f}×

Finding 1 — Top 10 complaint types by equity gap (Q1 vs Q5):
{gap_json}

Finding 2 — Borough × income quintile avg equity scores (1.0 = city average):
{heatmap_json}

Finding 3 — Monthly equity trend Q1 vs Q5:
{trend_json}

Equity by Income page — avg P90 hours and equity score by income quintile (all complaint types):
{quintile_p90_json}

Complaint Type Breakdown page — top 10 complaint types by total volume:
{top_complaints_json}

Borough Map page — top 3 slowest complaint types per borough (500+ requests):
{borough_complaint_json}

Agency Breakdown page — total requests, Q1 avg equity, Q5 avg equity, and gap per agency (sorted by gap desc):
{agency_json}

Produce a root-cause assessment and actionable recommendations.\
"""
        st.info("No AI synthesis stored yet for the current data.")
        if st.button("Generate AI Analysis", type="primary"):
            # Claim the slot first — prevents any concurrent click from also calling Groq
            claimed = _claim_slot(data_hash)
            if claimed:
                with st.spinner("Generating…"):
                    try:
                        text = _call_groq(prompt)
                        _store_synthesis(data_hash, text)
                        # Rerun now — _load_cached_synthesis will read 'complete'
                        # from Snowflake, render the synthesis, and skip the button
                        st.rerun()
                    except Exception as exc:
                        # Release the lock so the user can retry
                        _store_synthesis(data_hash, "")
                        st.error(f"Groq error: {exc}")
            else:
                st.info("Another session is already generating. Refresh in a few seconds.")

else:
    st.info("Run the pipeline to populate findings data.")
