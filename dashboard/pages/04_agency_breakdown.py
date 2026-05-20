import re
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.snowflake_conn import run_query
from utils.styles import inject_css

inject_css()

st.header("Agency Breakdown — Volume & Equity Gap")
st.markdown("""
Groups all 311 complaint types by the city agency responsible for resolving them.
Shows each agency's total request volume, how Q1 (lowest income) and Q5 (highest income)
tracts are served, and the equity gap between them.
""")

# ── Complaint type → agency mapping (hardcoded) ───────────────────────────────
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

# ── Date range filter ─────────────────────────────────────────────────────────
_DEFAULT_START = "2020-01-01"
_DEFAULT_END   = date.today().strftime("%Y-%m-%d")
_DATE_RE       = re.compile(r"^\d{4}-\d{2}-\d{2}$")

st.caption("📅 Date range · Format: YYYY-MM-DD · e.g. 2023-01-01")
_dc1, _dc2, _dc3 = st.columns([2, 2, 1])
_start_input = _dc1.text_input("Start date", value=_DEFAULT_START, key="ab_start")
_end_input   = _dc2.text_input("End date",   value=_DEFAULT_END,   key="ab_end")
if _dc3.button("↺ Reset", key="ab_reset", use_container_width=True):
    st.session_state.pop("ab_start", None)
    st.session_state.pop("ab_end",   None)
    st.rerun()

start_date = _start_input if _DATE_RE.match(_start_input or "") else _DEFAULT_START
end_date   = _end_input   if _DATE_RE.match(_end_input   or "") else _DEFAULT_END

# ── Query — all quintiles so we can sum total volume accurately ───────────────
sql = f"""
SELECT
    complaint_type,
    income_quintile,
    SUM(request_count) AS total_requests,
    AVG(equity_score)  AS avg_equity_score
FROM MARTS.FCT_EQUITY_SPLITS
WHERE request_month BETWEEN '{start_date}' AND '{end_date}'
GROUP BY complaint_type, income_quintile
"""
raw = run_query(sql)

if raw.empty:
    st.warning("No data for this date range.")
    st.stop()

# ── Map complaint types to agencies ──────────────────────────────────────────
raw["agency"] = raw["complaint_type"].map(_AGENCY).fillna("Other")

# Total volume across all quintiles per agency
vol = raw.groupby("agency")["total_requests"].sum().rename("total_requests")

# Q1 and Q5 avg equity score per agency
q1 = (
    raw[raw["income_quintile"] == 1]
    .groupby("agency")["avg_equity_score"].mean()
    .rename("q1_avg_equity")
)
q5 = (
    raw[raw["income_quintile"] == 5]
    .groupby("agency")["avg_equity_score"].mean()
    .rename("q5_avg_equity")
)

# Combine
agency_df = pd.concat([vol, q1, q5], axis=1).dropna(subset=["q1_avg_equity", "q5_avg_equity"])
agency_df["gap"] = agency_df["q1_avg_equity"] - agency_df["q5_avg_equity"]
agency_df = agency_df.reset_index().rename(columns={"agency": "Agency"})
agency_df["total_requests"] = agency_df["total_requests"].astype(int)

# ── Agency filter ─────────────────────────────────────────────────────────────
all_agencies = sorted(agency_df["Agency"].unique())
selected_agencies = st.multiselect(
    "Filter by agency",
    options=all_agencies,
    default=all_agencies,
)
agency_df = agency_df[agency_df["Agency"].isin(selected_agencies)]

if agency_df.empty:
    st.warning("Select at least one agency.")
    st.stop()

# ── Sort control ──────────────────────────────────────────────────────────────
sort_by = st.radio(
    "Order by",
    ["Gap desc", "Total requests desc", "Gap desc, then total requests desc", "Total requests desc, then gap desc"],
    horizontal=True,
)
_sort_cols = {
    "Gap desc":                                    ["gap"],
    "Total requests desc":                         ["total_requests"],
    "Gap desc, then total requests desc":          ["gap", "total_requests"],
    "Total requests desc, then gap desc":          ["total_requests", "gap"],
}[sort_by]

agency_df = agency_df.sort_values(_sort_cols, ascending=False)

# ── Bar chart — equity gap by agency ─────────────────────────────────────────
fig = px.bar(
    agency_df,
    x="gap",
    y="Agency",
    color="gap",
    color_continuous_scale="RdYlGn_r",
    color_continuous_midpoint=0,
    orientation="h",
    hover_data={
        "total_requests":  True,
        "q1_avg_equity":   ":.3f",
        "q5_avg_equity":   ":.3f",
        "gap":             ":.3f",
    },
    labels={
        "gap":            "Equity Gap (Q1 − Q5)",
        "Agency":         "Agency",
        "total_requests": "Total Requests",
        "q1_avg_equity":  "Q1 Avg Equity",
        "q5_avg_equity":  "Q5 Avg Equity",
    },
    title="Equity Gap by Agency (Q1 avg equity score − Q5 avg equity score)",
)
fig.update_layout(coloraxis_showscale=False, yaxis_title=None, height=600)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Each bar is one agency. Bar length = equity gap (Q1 avg equity score minus Q5 avg equity score). "
    "A larger positive gap means the agency resolves complaints significantly slower in low-income tracts "
    "than in high-income ones. A gap near zero means the agency serves all income levels equally — "
    "though both may still be slow in absolute terms. Negative values mean Q5 tracts wait longer than Q1."
)

# ── Summary table ─────────────────────────────────────────────────────────────
st.markdown("**Agency summary table:**")
st.dataframe(
    agency_df[["Agency", "total_requests", "q1_avg_equity", "q5_avg_equity", "gap"]]
    .rename(columns={
        "total_requests": "Total Requests",
        "q1_avg_equity":  "Q1 Avg Equity",
        "q5_avg_equity":  "Q5 Avg Equity",
        "gap":            "Gap (Q1 − Q5)",
    })
    .sort_values(
        ["Gap (Q1 − Q5)", "Total Requests"] if "total requests" in sort_by.lower() or "then" in sort_by.lower()
        else ["Gap (Q1 − Q5)"] if "gap" in sort_by.lower()
        else ["Total Requests"],
        ascending=False,
    )
    .reset_index(drop=True),
    use_container_width=True,
)
