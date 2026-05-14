from collections import defaultdict

import pandas as pd
import streamlit as st

from utils.snowflake_conn import run_query
from utils.styles import inject_css

BACK_TO_TOP = '[↑ Back to top](#top)'

st.set_page_config(
    page_title="NYC 311 Service Equity",
    page_icon="🗽",
    layout="wide",
)

inject_css()

st.markdown('<a name="top"></a>', unsafe_allow_html=True)
st.title("NYC 311 Service Equity Dashboard")
st.markdown("### Does your neighborhood get fair service from the city?")

st.markdown("""
This dashboard investigates whether New York City responds to resident complaints at the same
speed regardless of neighborhood wealth. The short answer — it doesn't always.
""")

# ── Hero stats ────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
col1.markdown("""
<div class="hero-stat">
  <div class="number">3M+</div>
  <div class="label">311 requests per year</div>
</div>
""", unsafe_allow_html=True)
col2.markdown("""
<div class="hero-stat">
  <div class="number">2,168</div>
  <div class="label">Census tracts analyzed</div>
</div>
""", unsafe_allow_html=True)
col3.markdown("""
<div class="hero-stat">
  <div class="number">2020–now</div>
  <div class="label">Dataset coverage</div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
**On this page:**
[What is 311?](#what-is-311) ·
[The Problem](#the-problem) ·
[What is a Census Tract?](#what-is-a-census-tract) ·
[Key Metrics Explained](#key-metrics-explained) ·
[How to Navigate](#how-to-navigate-this-dashboard) ·
[Data Sources](#data-sources)
""")

st.divider()

# ── What is 311 + Complaint Type Reference ───────────────────────────────────
st.subheader("What is 311?")
st.markdown("""
**311** is New York City's non-emergency government helpline. Residents call or submit requests
online to report problems that need city attention — a broken street light, a rat infestation,
no heat in an apartment in January, a blocked driveway. The city receives over **3 million
requests per year**.

When a request is submitted, it is tagged with a **complaint type** that routes it to the
relevant city agency (NYPD, Health Department, Department of Buildings, etc.). The time between
submission and resolution is the **response time** — the key metric in this dashboard.

Use the table below to understand what each complaint type actually means, which agency handles
it, and what a resident would be reporting. Use the search box to find a specific type.
""")

COMPLAINT_TYPES = {
    "🐀 Pests & Animals": {
        "ANIMAL IN A PARK": ("Wild or stray animal loose in a park that may be dangerous or injured.", "Parks"),
        "ANIMAL-ABUSE": (
            "Reports of animals being mistreated, neglected, or in distress.\n"
            "Handled by NYC Animal Care Centers.",
            "NYPD/ACC"),
        "DEAD ANIMAL": ("Dead animal on a public street, sidewalk, or park. City removes it.", "Sanitation"),
        "MOSQUITOES": (
            "Standing water or mosquito breeding sites in public areas,\n"
            "especially relevant for West Nile virus prevention.",
            "Health"),
        "POISON IVY": (
            "Poison ivy or other toxic plants growing in a public park or on city property.\n"
            "Reported to Parks Department for removal.",
            "Parks"),
    },
    "🌡️ Housing & Building Conditions": {
        "DOOR/WINDOW": (
            "Broken doors, windows, or locks in a residential building\n"
            "that compromise security or safety.",
            "HPD"),
        "ELEVATOR": (
            "Broken or unsafe elevator in a residential building.\n"
            "Elevators in NYC buildings over 5 floors are legally required to be maintained.",
            "HPD"),
        "FLOORING/STAIRS": (
            "Broken, rotted, or dangerous floors or stairs inside a residential building.\n"
            "Structural hazard for residents.",
            "HPD"),
        "HEAT/HOT WATER": (
            "Tenant has no heat or hot water.\n"
            "NYC law requires landlords to provide heat (68°F) Oct 1–May 31\n"
            "and hot water year-round. One of the most time-sensitive complaint types.",
            "HPD"),
        "NON-RESIDENTIAL HEAT": (
            "No heat in a commercial or non-residential building such as a school,\n"
            "office, or community facility.",
            "HPD/DOB"),
        "OUTSIDE BUILDING": (
            "Unsafe or deteriorating conditions on the exterior of a building —\n"
            "crumbling facade, broken railings, exposed wiring on the outside.",
            "HPD/DOB"),
        "PAINT/PLASTER": (
            "Peeling paint or plaster in a residential unit —\n"
            "particularly hazardous if lead paint is present in pre-1960 buildings.",
            "HPD"),
        "PLUMBING": ("Leaking pipes, broken fixtures, or no running water in a residential unit.", "HPD"),
        "UNSANITARY CONDITION": (
            "General unsanitary conditions in a residential building —\n"
            "cockroaches, bedbugs, garbage accumulation, vermin other than rats.",
            "HPD"),
        "WATER LEAK": (
            "Active water leak from pipes, ceiling, or roof inside or outside a building.\n"
            "Distinct from no-water complaints — water is present but leaking.",
            "HPD/DEP"),
        "WATER SYSTEM": (
            "No water supply, discolored water, or water pressure problems\n"
            "in a residential building.",
            "HPD/DEP"),
    },
    "🍽️ Food, Health & Consumer": {
        "CONSUMER COMPLAINT": (
            "Complaint about a business engaging in deceptive or unfair practices —\n"
            "false advertising, price gouging, unlicensed operation.\n"
            "Handled by the Department of Consumer and Worker Protection.",
            "DCWP"),
        "DRINKING": (
            "Public drinking of alcohol in an area where it is prohibited,\n"
            "such as a park or street corner.",
            "NYPD"),
        "FOOD ESTABLISHMENT": (
            "Unsanitary conditions inside a restaurant, café, food truck,\n"
            "or any licensed food business.\n"
            "Covers: pest sightings, improper food storage, employee hygiene violations,\n"
            "dirty kitchen conditions.\n"
            "NOT for food quality or bad service — those are not city health violations.",
            "Health"),
        "MOBILE FOOD VENDOR": (
            "Complaint about a street food cart or truck —\n"
            "operating without a permit, blocking the sidewalk,\n"
            "or unsanitary food handling.",
            "Health/DCWP"),
        "SMOKING OR VAPING": (
            "Smoking or vaping in a prohibited area —\n"
            "parks, playgrounds, beaches, building entrances, or restaurants.",
            "Health/NYPD"),
        "TATTOOING": (
            "Unlicensed or unsanitary tattooing or body piercing operation.\n"
            "Handled by the NYC Department of Health.",
            "Health"),
        "AIR QUALITY": (
            "Outdoor air quality concerns —\n"
            "smoke, dust, chemical fumes, or odors from industrial sources or construction.",
            "DEP"),
        "WATER CONSERVATION": (
            "Water being wasted or misused — open fire hydrants, broken sprinkler systems,\n"
            "or illegal water connections.",
            "DEP"),
    },
    "🔊 Noise": {
        "NOISE": (
            "General noise complaint not fitting a specific subcategory.\n"
            "Used when the source is unclassified or mixed.",
            "NYPD"),
        "NOISE - COMMERCIAL": (
            "Excessive noise from a commercial business —\n"
            "bar, restaurant, club, retail store.",
            "NYPD"),
        "NOISE - HOUSE OF WORSHIP": (
            "Excessive amplified sound from a church, mosque, temple,\n"
            "or other religious venue.",
            "NYPD"),
        "NOISE - PARK": ("Noise from within or near a city park.", "Parks/NYPD"),
        "NOISE - RESIDENTIAL": (
            "Excessive noise coming from inside a residential building —\n"
            "loud music, parties, TV. Most common noise complaint type.",
            "NYPD"),
        "NOISE - STREET/SIDEWALK": (
            "Noise from people on the street —\n"
            "crowds, street performers, gatherings.",
            "NYPD"),
        "NOISE - VEHICLE": (
            "Noise from a car, truck, or motorcycle —\n"
            "engine revving, car alarm, loud exhaust.",
            "NYPD"),
        "ILLEGAL FIREWORKS": (
            "Fireworks being set off illegally outside of permitted dates or locations.\n"
            "Common around holidays.",
            "NYPD/FDNY"),
    },
    "🚗 Streets & Vehicles": {
        "ABANDONED BIKE": (
            "Bicycle left locked or unlocked on public property for an extended period,\n"
            "blocking sidewalk access or otherwise abandoned.",
            "Sanitation"),
        "ABANDONED VEHICLE": (
            "Car, truck, or motorcycle left on a public street for more than 72 hours\n"
            "with no valid registration or signs of use.",
            "NYPD/Sanitation"),
        "BIKE/ROLLER/SKATE": (
            "Cyclists, skaters, or skateboarders riding unsafely or in prohibited areas —\n"
            "sidewalks, parks, pedestrian plazas.",
            "NYPD"),
        "BLOCKED DRIVEWAY": ("A vehicle is blocking access to a private driveway.", "NYPD"),
        "CURB CONDITION": (
            "Damaged or missing curb cut,\n"
            "particularly affecting wheelchair accessibility.",
            "DOT"),
        "DERELICT VEHICLES": (
            "Multiple or commercial abandoned vehicles on a public street or lot.\n"
            "Similar to Abandoned Vehicle but often refers to junked or stripped cars.",
            "NYPD/Sanitation"),
        "ILLEGAL PARKING": (
            "Car parked illegally — blocking a fire hydrant, crosswalk, bus stop, or bike lane.\n"
            "Also double parking or parking on a sidewalk.",
            "NYPD/DOT"),
        "OBSTRUCTION": (
            "Something blocking a public sidewalk, street, or entrance —\n"
            "scaffolding without a permit, dumpster in the road, construction debris.",
            "DOT/DOB"),
        "SIDEWALK CONDITION": ("Broken, uneven, or dangerous sidewalk surface.", "DOT"),
        "STREET CONDITION": ("Pothole, cracked pavement, sunken road, or unsafe street surface.", "DOT"),
        "STREET SIGN - DAMAGED": ("A street name or regulatory sign that is bent, faded, or unreadable.", "DOT"),
        "STREET SIGN - MISSING": ("A street name or regulatory sign that has been removed or stolen.", "DOT"),
        "TRAFFIC": (
            "General traffic issue not covered by other categories —\n"
            "dangerous intersection, inadequate signage, jaywalking concerns.",
            "DOT/NYPD"),
        "TRAFFIC SIGNAL CONDITION": ("Broken, dark, or malfunctioning traffic light.", "DOT"),
    },
    "🗑️ Sanitation & Environment": {
        "COMMERCIAL DISPOSAL COMPLAINT": (
            "A business is illegally disposing of waste —\n"
            "dumping trash on the street, using residential bins, or violating disposal rules.",
            "Sanitation"),
        "DEAD/DYING TREE": (
            "A city-owned street tree that is dead, dying, or structurally unstable.\n"
            "Risk of falling branches or trunk collapse.",
            "Parks"),
        "DIRTY CONDITION": (
            "Garbage, litter, or debris on a public street, sidewalk, or lot.\n"
            "Most common sanitation complaint.",
            "Sanitation"),
        "GRAFFITI": ("Vandalism graffiti on a public surface, building facade, or city property.", "Sanitation/Parks"),
        "ILLEGAL DUMPING": (
            "Someone is illegally dumping bulk waste, furniture, construction debris,\n"
            "or bags of garbage in a public space or vacant lot.",
            "Sanitation"),
        "ILLEGAL TREE DAMAGE": (
            "A city-owned street tree has been damaged or cut without a permit.\n"
            "NYC trees are protected — unauthorized pruning or removal is a violation.",
            "Parks"),
        "LITTER BASKET COMPLAINT": (
            "Public trash can on a street corner or park that is full, damaged,\n"
            "or needs attention.",
            "Sanitation"),
        "LITTER BASKET REQUEST": (
            "Request for a new public trash can to be installed\n"
            "at a location that currently lacks one.",
            "Sanitation"),
        "MISSED COLLECTION": (
            "Garbage, recycling, or compost that was placed out correctly\n"
            "but not collected on the scheduled pickup day.",
            "Sanitation"),
        "OVERGROWN TREE/BRANCHES": (
            "City-owned tree branches overhanging the street, blocking signs,\n"
            "or interfering with power lines.",
            "Parks"),
        "RESIDENTIAL DISPOSAL COMPLAINT": (
            "A resident is improperly disposing of household waste —\n"
            "putting trash out too early, wrong bins, bulk items without scheduling.",
            "Sanitation"),
        "SANITATION WORKER OR VEHICLE COMPLAINT": (
            "Complaint about a sanitation worker's conduct or a city garbage truck —\n"
            "reckless driving, missed stop, worker misconduct.",
            "Sanitation"),
        "SEWER": (
            "Blocked, overflowing, or broken sewer drain\n"
            "causing flooding or odor on a street.",
            "DEP"),
        "STREET SWEEPING COMPLAINT": (
            "Street sweeper did not clean a block on its scheduled day,\n"
            "or a car was ticketed despite the block not being swept.",
            "Sanitation/DOT"),
        "WOOD PILE REMAINING": (
            "Cut wood or tree debris left on a public street or sidewalk\n"
            "after tree removal work, not cleaned up by the contractor.",
            "Parks/Sanitation"),
    },
    "🏠 Homeless, Safety & Social Services": {
        "DISORDERLY YOUTH": (
            "Group of young people behaving in a disruptive or threatening manner\n"
            "in a public area.",
            "NYPD"),
        "DRUG ACTIVITY": ("Suspected drug use or dealing in a public area.", "NYPD"),
        "ENCAMPMENT": (
            "Group of people living in a tent, makeshift shelter,\n"
            "or encampment on public property.",
            "DHS/NYPD"),
        "HOMELESS PERSON ASSISTANCE": (
            "Individual experiencing homelessness who may need outreach services —\n"
            "not an emergency.",
            "DHS"),
        "NON-EMERGENCY POLICE MATTER": (
            "A situation requiring police awareness but not an emergency —\n"
            "suspicious activity, minor disputes, quality of life concerns.",
            "NYPD"),
        "PANHANDLING": (
            "Aggressive or persistent solicitation of money in a public space.\n"
            "Passive panhandling is generally not actionable.",
            "NYPD"),
        "URINATING IN PUBLIC": (
            "Person urinating or defecating in a public space.\n"
            "A quality-of-life violation handled by NYPD.",
            "NYPD"),
        "VENDOR ENFORCEMENT": (
            "Unlicensed street vendor, or a licensed vendor operating outside\n"
            "their permitted location or hours.",
            "DCWP/NYPD"),
        "VIOLATION OF PARK RULES": (
            "Any rule violation inside a city park — alcohol, BBQ in prohibited areas,\n"
            "unleashed dogs, trespassing after hours.",
            "Parks"),
    },
    "🏗️ Buildings, Utilities & Maintenance": {
        "APPLIANCE": (
            "Broken or malfunctioning appliance provided by the landlord —\n"
            "stove, refrigerator, or heat system appliance in a rental unit.",
            "HPD"),
        "DAY CARE": (
            "Complaint about a day care or childcare facility —\n"
            "unsafe conditions, overcrowding, unlicensed operation,\n"
            "or violations of health and safety standards.",
            "ACS/Health"),
        "ELECTRIC": (
            "Electrical hazard or outage in a residential building —\n"
            "exposed wiring, no electricity, flickering power.",
            "HPD/ConEd"),
        "ELECTRICAL": (
            "Electrical issue in a commercial or public space —\n"
            "similar to Electric but typically filed for non-residential locations.",
            "DOB/ConEd"),
        "EMERGENCY RESPONSE TEAM (ERT)": (
            "Structural emergency —\n"
            "collapsed ceiling, imminent danger from a building.",
            "DOB/FDNY"),
        "GENERAL": (
            "Catch-all category for complaints that do not fit a specific type.\n"
            "Often reassigned to a specific agency after review.",
            "Various"),
        "GENERAL CONSTRUCTION/PLUMBING": (
            "Construction or plumbing work being done without a permit,\n"
            "outside permitted hours, or in an unsafe manner.",
            "DOB"),
        "MAINTENANCE OR FACILITY": (
            "City-owned facility or infrastructure in need of maintenance —\n"
            "broken equipment in a park, pothole in a city parking lot,\n"
            "damaged city building.",
            "Various"),
        "SAFETY": (
            "General safety hazard in a public space or building\n"
            "not covered by a more specific category.",
            "Various"),
    },
}

# Flat lookup: complaint_type → (description, agency, category) for O(1) access
_LOOKUP: dict[str, tuple[str, str, str]] = {
    ctype: (desc, agency, cat)
    for cat, complaints in COMPLAINT_TYPES.items()
    for ctype, (desc, agency) in complaints.items()
}


@st.cache_data(ttl=3600)
def _live_complaint_types() -> list[str]:
    """Distinct complaint types present in Snowflake, sorted alphabetically."""
    try:
        return (
            run_query("SELECT DISTINCT complaint_type FROM MARTS.FCT_EQUITY_SPLITS ORDER BY 1")[
                "complaint_type"
            ].tolist()
        )
    except Exception:
        # Snowflake unavailable — fall back to the hardcoded set so the page still renders
        return sorted(_LOOKUP.keys())


_live_types = _live_complaint_types()

# Partition live types into known (has a description) and uncategorized
_by_category: dict[str, list[str]] = defaultdict(list)
_uncategorized: list[str] = []
for _t in _live_types:
    if _t in _LOOKUP:
        _by_category[_LOOKUP[_t][2]].append(_t)
    else:
        _uncategorized.append(_t)


with st.expander("Show all complaint types and what they mean"):
    st.markdown(
        "**Agency abbreviations:** HPD = Housing Preservation & Development · "
        "DOB = Dept of Buildings · DEP = Dept of Environmental Protection · "
        "DOT = Dept of Transportation · DHS = Dept of Homeless Services · "
        "TLC = Taxi & Limousine Commission · FDNY = Fire Dept · "
        "NYPD = Police Dept · ACC = Animal Care Centers"
    )
    st.markdown("---")

    search = st.text_input("🔍 Search complaint types", placeholder="e.g. food, noise, heat...")
    q = search.strip().lower()

    # ── Described categories (preserve original display order) ────────────────
    for category in COMPLAINT_TYPES:
        types_in_cat = _by_category.get(category, [])
        rows = []
        for ctype in types_in_cat:
            desc, agency, _ = _LOOKUP[ctype]
            if not q or q in ctype.lower() or q in desc.lower():
                rows.append({"Complaint Type": ctype, "What it means": desc, "Agency": agency})
        if not rows:
            continue
        st.markdown(f"**{category}**")
        # st.table wraps text naturally — st.dataframe clips long text at fixed row height
        st.table(pd.DataFrame(rows).set_index("Complaint Type"))

    # ── Types in Snowflake that have no hardcoded description yet ─────────────
    if _uncategorized:
        unc_rows = [
            {
                "Complaint Type": t,
                "What it means": (
                    "A valid NYC 311 complaint category. "
                    "Detailed description not yet available in this reference."
                ),
                "Agency": "Various",
            }
            for t in _uncategorized
            if not q or q in t.lower()
        ]
        if unc_rows:
            st.markdown("**📋 Other / Uncategorized**")
            st.table(pd.DataFrame(unc_rows).set_index("Complaint Type"))

st.markdown(BACK_TO_TOP)
st.divider()

# ── The Problem ───────────────────────────────────────────────────────────────
st.subheader("The Problem")
st.markdown("""
The question this dashboard asks is simple: **does the city respond equally fast to everyone?**

Research and resident experience suggest the answer is no. Neighborhoods with lower household
incomes tend to wait longer for the same types of complaints to be resolved compared to wealthier
neighborhoods — even when the complaints are identical. This is a **service equity** problem.
""")


st.markdown(BACK_TO_TOP)
st.divider()

# ── What is a Census Tract ────────────────────────────────────────────────────
st.subheader("What is a Census Tract?")

col1, col2 = st.columns([2, 1])
with col1:
    st.markdown("""
    New York City is divided into **2,168 census tracts** — small geographic units defined by
    the US Census Bureau. Each tract contains roughly **1,200 to 8,000 people**.

    Think of census tracts as the city's smallest official neighborhood units. They are:
    - Smaller than ZIP codes
    - More precise than borough-level analysis
    - Stable enough to track changes over time

    The US Census Bureau surveys every census tract every year through the
    **American Community Survey (ACS)** — collecting data on income, population, poverty rates,
    and demographics. This dashboard uses that data to assign each tract an **income quintile**:

    | Quintile | Meaning | Approx. median income |
    |---|---|---|
    | 1 | Lowest income — bottom 20% of tracts | Below ~$35,000/year |
    | 2 | Lower-middle income | ~$35,000–$55,000 |
    | 3 | Middle income | ~$55,000–$75,000 |
    | 4 | Upper-middle income | ~$75,000–$100,000 |
    | 5 | Highest income — top 20% of tracts | Above ~$100,000 |

    > **Example:** Brownsville, Brooklyn is a quintile 1 tract.
    > The Upper East Side, Manhattan is a quintile 5 tract.
    > This dashboard measures whether they receive the same quality of 311 service.
    """)
with col2:
    st.info("""
    **NYC's 5 Boroughs:**

    🟫 **Manhattan** — densely packed island, home to both the wealthiest and some of the
    poorest neighborhoods in the city

    🟧 **Brooklyn** — most populous borough, wide income diversity from Brownsville to
    Brooklyn Heights

    🟨 **Queens** — most ethnically diverse borough, large immigrant communities

    🟥 **The Bronx** — highest poverty rate of any US urban county

    🟩 **Staten Island** — least densely populated, predominantly suburban character
    """)

st.markdown(BACK_TO_TOP)
st.divider()

# ── Key Metrics Explained ─────────────────────────────────────────────────────
st.subheader("Key Metrics Explained")

st.markdown("##### Response Time")
st.markdown("""
Response time is measured in **hours** from when a 311 request is submitted to when the
assigned agency marks it as resolved.

This dashboard uses **percentiles** rather than averages because averages are easily skewed
by extreme outliers (a single complaint that took 6 months would distort the whole borough's average).

| Metric | What it means |
|---|---|
| **P50 (median)** | Half of complaints resolve faster than this, half slower — the typical experience |
| **P75** | 75% of complaints resolve within this time |
| **P90** | 90% of complaints resolve within this time — captures the worst-case experience |

This dashboard focuses on **P90** because it best captures whether the *worst-served* residents
in a neighborhood are being left behind.
""")

st.markdown("##### Equity Score")
st.markdown("""
The equity score is the core metric of this dashboard. It is calculated as:

> **Equity Score = This tract's P90 response time ÷ City-wide P90 for the same complaint type**

| Score | Meaning |
|---|---|
| `1.0` | This tract's worst-case wait time exactly matches the city average |
| `1.5` | Residents here wait 50% longer than the city average |
| `2.0` | Residents here wait twice as long as the city average |
| `0.8` | Residents here actually wait less than the city average (faster service) |

An equity score consistently above 1.0 for lower-income tracts — and below 1.0 for
higher-income tracts — is evidence of a **systematic service disparity**.
""")

st.markdown(BACK_TO_TOP)
st.divider()

# ── How to Navigate ───────────────────────────────────────────────────────────
st.subheader("How to Navigate This Dashboard")

st.markdown("""
Use the **sidebar on the left** to switch between pages:

| Page | What it shows |
|---|---|
| 🗺️ **Borough Map** | A color-coded map of every NYC census tract. Green tracts receive on-par or better service. Red tracts wait significantly longer. Filter by complaint type and borough to focus on specific issues. |
| 📊 **Equity by Income** | Bar charts and scatter plots showing whether lower-income quintiles wait longer than higher-income ones for the same complaint type. The equity ratio callout gives a single number summary. |
| 🔥 **Complaint Breakdown** | A heatmap of the top 20 complaint types across all 5 boroughs. Reveals which categories have the worst response times and where. |
| 🔍 **Key Findings** | Three specific findings drawn from the data — rodent complaint gaps by income, heat complaint disparities by borough in winter, and how the equity gap has changed over time. |

**Start with the Borough Map** — select a complaint type you care about and look for clusters
of red tracts. Then use the Equity by Income page to quantify the gap, and the Key Findings
page to see the headline numbers.
""")

st.markdown(BACK_TO_TOP)
st.divider()

# ── Data Sources ──────────────────────────────────────────────────────────────
st.subheader("Data Sources")
st.markdown("""
| Source | What it provides | Updated |
|---|---|---|
| [NYC Open Data — 311 Service Requests](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9) | Every 311 request submitted to the city | Daily |
| [US Census Bureau — ACS 5-Year Estimates](https://www.census.gov/programs-surveys/acs) | Tract-level demographics: income, population, poverty | Annually |
| [NYC Census Tract Boundaries](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html) | Geographic boundaries for each census tract | Decennial |

All data is processed through an automated pipeline that ingests new 311 requests daily,
joins them to their census tract using GPS coordinates, and recomputes equity metrics across
all tracts. The dashboard reflects the most recent data loaded.
""")

st.markdown(BACK_TO_TOP)
st.caption("Built with Socrata API · AWS S3 · Snowflake · dbt · Great Expectations · Streamlit")
