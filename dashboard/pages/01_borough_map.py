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
    roughly 1,200–8,000 residents. The color represents the **equity score** for the selected complaint type.

    **Equity score:**
    - `1.0` = this tract's P90 response time exactly matches the city average
    - `> 1.0` = slower than average (e.g. `2.5` = residents wait 2.5× longer than the city median)
    - `< 1.0` = faster than average

    **Color scale:**
    - 🟢 Green — at or below city average (equity score ≤ 1.0)
    - 🟡 Yellow — at the city average (equity score = 1.0)
    - 🔴 Red — significantly above average
    The scale adapts to the current data so color differences are always meaningful.

    **Navigating the map:**
    - Scroll to zoom in/out · Click and drag to pan
    - **Hover** over any tract to see its borough, tract number, equity score, response times, and complaint count
    - Use the **Complaint type** dropdown to switch categories
    - Use the **Borough** multiselect to narrow the view
    - Grey tracts have no data for the selected complaint type

    **P90 explained:**
    P90 is the 90th percentile response time — 90% of complaints in that tract resolved within
    this many hours. It captures the worst-case experience rather than the average.
    """)

COMPLAINT_QUERY = "SELECT DISTINCT complaint_type FROM MARTS.FCT_EQUITY_SPLITS ORDER BY 1"
boroughs = ["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]

complaint_types = run_query(COMPLAINT_QUERY)["complaint_type"].tolist()

col1, col2 = st.columns(2)
selected_complaint = col1.selectbox("Complaint type", complaint_types, index=0)
selected_boroughs = col2.multiselect("Borough", boroughs, default=boroughs)

borough_filter = "', '".join(selected_boroughs)
sql = f"""
SELECT
    tract_geoid,
    complaint_type,
    AVG(p50_hours)               AS p50_hours,
    AVG(p75_hours)               AS p75_hours,
    AVG(p90_hours)               AS p90_hours,
    AVG(equity_score)            AS equity_score,
    SUM(request_count)           AS complaint_count,
    MAX(median_household_income) AS median_household_income,
    MAX(income_quintile)         AS income_quintile
FROM MARTS.FCT_EQUITY_SPLITS
WHERE complaint_type = '{selected_complaint}'
  AND borough IN ('{borough_filter}')
GROUP BY tract_geoid, complaint_type
"""
df = run_query(sql)

if df.empty:
    st.warning("No data for this selection.")
    st.stop()

# Neighborhood name from NTA crosswalk; falls back to county name if lookup fails
_nta = _load_nta_lookup()
df["county"] = df["tract_geoid"].apply(_county_from_geoid)
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

fig = px.choropleth_mapbox(
    df,
    geojson=geojson,
    locations="tract_geoid",
    featureidkey="properties.tract_geoid",
    color="equity_score",
    color_continuous_scale="RdYlGn_r",
    # No fixed range — scale adapts to actual data distribution so close values
    # remain visually distinguishable. Midpoint pinned at 1.0 so yellow = city average.
    color_continuous_midpoint=1.0,
    mapbox_style="carto-positron",
    zoom=10,
    center={"lat": 40.7128, "lon": -74.0060},
    opacity=0.7,
    hover_data={
        "neighborhood": True,
        "county": True,
        "tract_geoid": False,
        "equity_score": ":.2f",
        "p50_hours": ":.1f",
        "p90_hours": ":.1f",
        "complaint_count": True,
    },
    labels={
        "equity_score": "Equity Score",
        "neighborhood": "Neighborhood",
        "county": "County",
        "p50_hours": "P50 (hrs)",
        "p90_hours": "P90 (hrs)",
        "complaint_count": "Complaints",
    },
    title=f"Equity Score — {selected_complaint}",
)
fig.update_layout(margin={"r": 0, "t": 40, "l": 0, "b": 0}, height=600)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Equity score = tract P90 / city-wide P90. "
    "Green = at or below city average · Yellow = city average (1.0) · Red = above average. "
    "Color scale adapts to current data — differences between close values are always visible."
)
