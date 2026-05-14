import logging
import requests
import pandas as pd

logger = logging.getLogger(__name__)

# ACS 5-Year variables: median income, total pop, poverty, race/ethnicity
ACS_VARIABLES = [
    "GEO_ID",
    "B19013_001E",  # median household income
    "B01003_001E",  # total population
    "B17001_002E",  # population below poverty
    "B03002_003E",  # white non-hispanic
    "B03002_012E",  # hispanic
    "B03002_004E",  # black
]

# NYC county FIPS codes (Bronx=005, Brooklyn=047, Manhattan=061, Queens=081, Staten Island=085)
NYC_COUNTIES = ["005", "047", "061", "081", "085"]


def fetch_nyc_acs(api_key: str, vintage_year: int = 2022) -> pd.DataFrame:
    """Pull ACS 5-Year tract-level demographics for all NYC counties.
    Returns one row per census tract."""
    frames = []

    for county in NYC_COUNTIES:
        url = (
            f"https://api.census.gov/data/{vintage_year}/acs/acs5"
            f"?get={','.join(ACS_VARIABLES)}"
            f"&for=tract:*"
            f"&in=state:36+county:{county}"
            f"&key={api_key}"
        )
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        cols = [c.lower() for c in data[0]]
        df = pd.DataFrame(data[1:], columns=cols)
        df["county_fips"] = county
        frames.append(df)
        logger.info("Fetched ACS for county %s: %d tracts", county, len(df))

    combined = pd.concat(frames, ignore_index=True)

    numeric_cols = [
        "b19013_001e",
        "b01003_001e",
        "b17001_002e",
        "b03002_003e",
        "b03002_012e",
        "b03002_004e",
    ]
    for col in numeric_cols:
        if col in combined.columns:
            combined[col] = pd.to_numeric(combined[col], errors="coerce")

    # Replace Census sentinel value -666666666 (missing/suppressed) with None
    combined[numeric_cols] = combined[numeric_cols].where(
        combined[numeric_cols] > -666_666_666, other=None
    )

    combined["vintage_year"] = vintage_year
    logger.info("ACS fetch complete: %d total tracts", len(combined))
    return combined
