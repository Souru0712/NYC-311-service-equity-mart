"""
One-time ACS demographics load.
Run from the project root:

    python scripts/load_acs.py

Pulls US Census ACS 5-Year tract-level demographics for all NYC counties,
writes to S3, and loads into Snowflake RAW.ACS_DEMOGRAPHICS.

ACS releases each December with a ~13-month lag:
  2024 vintage (covering 2020-2024) → released December 2025  ← current
  2025 vintage (covering 2021-2025) → releases December 2026

Requires CENSUS_API_KEY in .env.
After the initial load, this is handled annually by dag_acs_annual.py.
"""
import sys
import warnings

# snowflake-connector-python uses a deprecated pandas API internally — suppress until connector is updated
warnings.filterwarnings("ignore", category=FutureWarning, module="snowflake")

sys.path.insert(0, ".")

from ingestion.config import Config
from ingestion.acs_client import fetch_nyc_acs
from ingestion.s3_writer import write_parquet_to_s3
from ingestion.snowflake_loader import get_connection, create_raw_acs_table, truncate_and_load_acs


def main() -> None:
    cfg = Config()

    # 2024 vintage covers survey responses from 2020-2024.
    # Released December 2025 — latest available as of May 2026.
    vintage_year = 2024
    coverage_start = vintage_year - 4

    print(f"Fetching ACS {vintage_year} 5-year estimates "
          f"(survey years {coverage_start}–{vintage_year}) for NYC census tracts ...")
    df = fetch_nyc_acs(api_key=cfg.census_api_key, vintage_year=vintage_year)
    print(f"  Fetched {len(df):,} tracts  (expect 2,300–2,400 — includes water-only and special tracts)")

    print(f"Writing to S3 ...")
    s3_uri = write_parquet_to_s3(
        df,
        bucket=cfg.s3_bucket,
        prefix="raw/acs_demographics",
        run_date=f"year={vintage_year}",
        aws_access_key=cfg.aws_access_key,
        aws_secret_key=cfg.aws_secret_key,
        aws_region=cfg.aws_region,
    )
    print(f"  Written to: {s3_uri}")

    print("Loading into Snowflake RAW.ACS_DEMOGRAPHICS (full replace) ...")
    sf = get_connection(cfg)
    create_raw_acs_table(sf)
    truncate_and_load_acs(sf, df)
    sf.close()

    print(f"\nDone. Verify in Snowflake:")
    print(f"  SELECT COUNT(*), MAX(vintage_year) FROM NYC_311.RAW.ACS_DEMOGRAPHICS;")
    print(f"  -- Expect 2,300–2,400 rows | vintage_year = {vintage_year} | survey years {coverage_start}–{vintage_year}")


if __name__ == "__main__":
    main()
