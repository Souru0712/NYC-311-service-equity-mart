import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotly.express as px
import streamlit as st

from utils.snowflake_conn import run_query
from utils.styles import inject_css

inject_css()

# County FIPS → borough name (parsed from the 11-char census GEOID)
_COUNTY_BOROUGH = {
    "005": "Bronx",
    "047": "Brooklyn",
    "061": "Manhattan",
    "081": "Queens",
    "085": "Staten Island",
}


def _county_from_geoid(geoid: str) -> str:
    """Extract the borough name from the county FIPS portion of a census GEOID."""
    if len(geoid) < 5:
        return geoid
    return _COUNTY_BOROUGH.get(geoid[2:5], "NYC")


@st.cache_data(ttl=86400, show_spinner=False)
def _load_nta_lookup() -> dict[str, str]:
    """Fetch NYC DCP tract → NTA neighborhood name crosswalk from NYC Open Data.
    Returns {tract_geoid: neighborhood_name}. Falls back to empty dict on failure.
    """
    import requests
    try:
        rows = requests.get(
            "https://data.cityofnewyork.us/resource/hm78-6dwm.json?$limit=5000",
            timeout=10,
        ).json()
        return {r["geoid"]: r["ntaname"] for r in rows if "geoid" in r and "ntaname" in r}
    except Exception:
        return {}


st.header("Tract Choropleth — P90 Response Time & Equity Score")

with st.expander("How to read this map"):
    st.markdown("""
    **What you're looking at:**
    Each shaded polygon is a NYC census tract — a small neighborhood unit defined by the Census Bureau,
    roughly 1,200–8,000 residents. The color represents the **equity score** for the selected filter.

    **Equity score:**
    - `1.0` = this tract matches the **median** NYC tract
    - `> 1.0` = slower than the typical tract (e.g. `2.5` = residents wait 2.5× longer)
    - `< 1.0` = faster than the typical tract

    **Filter modes:**
    - **Complaint type** — equity score for one complaint category across all income levels
    - **Income quintile** — average equity score across all complaint types for the selected income group(s); Q1 = lowest income, Q5 = highest

    **Color scale:**
    - 🟢 Green — at or below city average (equity score ≤ 1.0)
    - 🟡 Yellow — at the city average (equity score = 1.0)
    - 🔴 Red — significantly above average
    """)

COMPLAINT_QUERY = "SELECT DISTINCT complaint_type FROM MARTS.FCT_EQUITY_SPLITS ORDER BY 1"
BOROUGHS = ["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]
QUINTILE_OPTIONS = ["Q1", "Q2", "Q3", "Q4", "Q5"]
QUINTILE_MAP = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "Q5": 5}

complaint_types = run_query(COMPLAINT_QUERY)["complaint_type"].tolist()

# ── Filter mode toggle ────────────────────────────────────────────────────────
filter_mode = st.radio(
    "Filter by",
    ["Complaint type", "Income quintile"],
    horizontal=True,
)

col1, col2 = st.columns(2)

if filter_mode == "Complaint type":
    selected_complaint = col1.selectbox("Complaint type", complaint_types, index=0)
    selected_quintiles = list(QUINTILE_MAP.values())  # all quintiles included
    selected_quintile_labels = QUINTILE_OPTIONS
else:
    selected_quintile_labels = col1.multiselect(
        "Income quintile",
        QUINTILE_OPTIONS,
        default=QUINTILE_OPTIONS,
    )
    selected_quintiles = [QUINTILE_MAP[q] for q in selected_quintile_labels]
    selected_complaint = None

selected_boroughs = col2.multiselect("Borough", BOROUGHS, default=BOROUGHS)

# ── Date range filter ─────────────────────────────────────────────────────────
_DEFAULT_START = "2020-01-01"
_DEFAULT_END   = date.today().strftime("%Y-%m-%d")
_DATE_RE       = re.compile(r"^\d{4}-\d{2}-\d{2}$")

st.caption("📅 Date range · Format: YYYY-MM-DD · e.g. 2023-01-01")
_dc1, _dc2, _dc3 = st.columns([2, 2, 1])
_start_input = _dc1.text_input("Start date", value=_DEFAULT_START, key="bm_start")
_end_input   = _dc2.text_input("End date",   value=_DEFAULT_END,   key="bm_end")
if _dc3.button("↺ Reset", key="bm_reset", use_container_width=True):
    st.session_state.pop("bm_start", None)
    st.session_state.pop("bm_end",   None)
    st.rerun()

start_date  = _start_input if _DATE_RE.match(_start_input or "") else _DEFAULT_START
end_date    = _end_input   if _DATE_RE.match(_end_input   or "") else _DEFAULT_END
date_filter = f"AND request_month BETWEEN '{start_date}' AND '{end_date}'"

# ── Validation ────────────────────────────────────────────────────────────────
if not selected_boroughs:
    st.warning("Select at least one borough.")
    st.stop()

if filter_mode == "Income quintile" and not selected_quintiles:
    st.warning("Select at least one income quintile.")
    st.stop()

# ── Query ─────────────────────────────────────────────────────────────────────
borough_filter   = "', '".join(selected_boroughs)
quintile_filter  = ", ".join(str(q) for q in selected_quintiles)

if filter_mode == "Complaint type":
    sql = f"""
    SELECT
        tract_geoid,
        complaint_type,
        AVG(p50_hours)               AS p50_hours,
        AVG(p90_hours)               AS p90_hours,
        AVG(equity_score)            AS equity_score,
        AVG(city_p90)                AS city_p90,
        SUM(request_count)           AS complaint_count,
        MAX(median_household_income) AS median_household_income,
        MAX(income_quintile)         AS income_quintile
    FROM MARTS.FCT_EQUITY_SPLITS
    WHERE complaint_type = '{selected_complaint}'
      AND borough IN ('{borough_filter}')
      {date_filter}
    GROUP BY tract_geoid, complaint_type
    """
    map_title = f"Equity Score — {selected_complaint}"
else:
    sql = f"""
    SELECT
        tract_geoid,
        AVG(p50_hours)               AS p50_hours,
        AVG(p90_hours)               AS p90_hours,
        AVG(equity_score)            AS equity_score,
        AVG(city_p90)                AS city_p90,
        SUM(request_count)           AS complaint_count,
        MAX(median_household_income) AS median_household_income,
        MAX(income_quintile)         AS income_quintile
    FROM MARTS.FCT_EQUITY_SPLITS
    WHERE income_quintile IN ({quintile_filter})
      AND borough IN ('{borough_filter}')
      {date_filter}
    GROUP BY tract_geoid
    """
    map_title = f"Equity Score — Income Quintile {', '.join(selected_quintile_labels)}"

df = run_query(sql)

if df.empty:
    st.warning("No data for this selection.")
    st.stop()

# ── Enrich with neighborhood names ────────────────────────────────────────────
_nta = _load_nta_lookup()
df["county"]       = df["tract_geoid"].apply(_county_from_geoid)
df["neighborhood"] = df["tract_geoid"].map(_nta).fillna(df["county"])


@st.cache_data(ttl=86400)
def load_tract_geojson() -> dict:
    """Load NYC census tract boundaries.
    Reads from the local cache written by the ingestion spatial join.
    Falls back to pygris (Census TIGER) if the cache file doesn't exist."""
    import json
    import os

    cache_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "ingestion", "data", "nyc_tracts.geojson")
    )

    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)

    from pygris import tracts
    NYC_COUNTIES = ["005", "047", "061", "081", "085"]
    gdf = tracts(state="NY", county=NYC_COUNTIES, year=2020, cb=True)
    gdf = gdf.to_crs("EPSG:4326")
    gdf["tract_geoid"] = gdf["GEOID"].astype(str)
    return json.loads(gdf[["tract_geoid", "geometry"]].to_json())


geojson = load_tract_geojson()

# ── Choropleth ────────────────────────────────────────────────────────────────
hover = {
    "neighborhood":          True,
    "county":                True,
    "tract_geoid":           False,
    "equity_score":          ":.2f",
    "p90_hours":             ":.1f",
    "city_p90":              ":.1f",
    "p50_hours":             ":.1f",
    "complaint_count":       True,
    "income_quintile":       True,
    "median_household_income": True,
}

labels = {
    "equity_score":            "Equity Score",
    "neighborhood":            "Neighborhood",
    "county":                  "Borough",
    "p50_hours":               "P50 (hrs)",
    "p90_hours":               "This tract P90 (hrs)",
    "city_p90":                "Median tract P90 (hrs)",
    "complaint_count":         "Complaints",
    "income_quintile":         "Income Quintile",
    "median_household_income": "Median Income ($)",
}

fig = px.choropleth_mapbox(
    df,
    geojson=geojson,
    locations="tract_geoid",
    featureidkey="properties.tract_geoid",
    color="equity_score",
    color_continuous_scale="RdYlGn_r",
    color_continuous_midpoint=1.0,
    mapbox_style="carto-positron",
    zoom=10,
    center={"lat": 40.7128, "lon": -74.0060},
    opacity=0.7,
    hover_data=hover,
    labels=labels,
    title=map_title,
)
fig.update_layout(margin={"r": 0, "t": 40, "l": 0, "b": 0}, height=600)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Equity score = this tract's P90 ÷ median tract P90 citywide (equal weight per tract, not per complaint). "
    "Score 1.0 = matches the typical NYC neighborhood. "
    "Green ≤ 1.0 · Yellow = 1.0 · Red > 1.0."
)
