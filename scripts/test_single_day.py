"""
Single-day end-to-end smoke test.
Run from the project root:

    python scripts/test_single_day.py

Fetches the last 24 hours from Socrata, spatial-joins to census tracts,
writes to S3, and loads into Snowflake RAW.SOCRATA_311.
Reads all credentials from .env — copy .env.example first if you haven't.

Run this first in Snowflake if re-running after a bad load:
    TRUNCATE TABLE NYC_311.RAW.SOCRATA_311;
"""
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

# Allow running from project root without installing the package
sys.path.insert(0, ".")

from ingestion.config import Config
from ingestion.s3_writer import write_parquet_to_s3
from ingestion.snowflake_loader import copy_311_from_s3, create_raw_311_table, get_connection
from ingestion.socrata_client import fetch_incremental, records_to_dataframe
from ingestion.tract_geometry import assign_tract_geoid, download_tract_geojson


def main() -> None:
    cfg = Config()

    # ── 1. Fetch last 24 hours from Socrata ──────────────────────────────────
    watermark = datetime.now(timezone.utc) - timedelta(hours=24)
    print(f"Fetching records updated since {watermark.strftime('%Y-%m-%d %H:%M UTC')} ...")

    frames = []
    for batch in fetch_incremental(cfg.socrata_app_token, cfg.socrata_dataset_id, watermark):
        frames.append(records_to_dataframe(batch))

    if not frames:
        print("No records returned — check your SOCRATA_APP_TOKEN or try a wider window.")
        sys.exit(1)

    df = pd.concat(frames, ignore_index=True)
    print(f"  Fetched {len(df):,} rows  |  columns: {list(df.columns)[:6]} ...")

    # ── 2. Spatial join to census tracts ─────────────────────────────────────
    print("Downloading / loading tract boundaries ...")
    tracts = download_tract_geojson(cfg.tract_geojson_cache)
    df = assign_tract_geoid(df, tracts)

    coverage = df["tract_geoid"].notna().mean()
    print(f"  tract_geoid coverage: {coverage:.1%}  (expect ~90–95%)")

    # ── 3. Write Parquet to S3 ────────────────────────────────────────────────
    print("Writing Parquet to S3 ...")
    s3_uri = write_parquet_to_s3(
        df,
        bucket=cfg.s3_bucket,
        prefix="raw/socrata_311",
        run_date="test-run",
        aws_access_key=cfg.aws_access_key,
        aws_secret_key=cfg.aws_secret_key,
        aws_region=cfg.aws_region,
    )
    print(f"  Written to: {s3_uri}")

    # ── 4. Load into Snowflake ────────────────────────────────────────────────
    print("Loading into Snowflake RAW.SOCRATA_311 ...")
    sf = get_connection(cfg)
    create_raw_311_table(sf)
    rows_loaded = copy_311_from_s3(sf, s3_uri, cfg.snowflake_stage)
    sf.close()
    print(f"  Rows loaded: {rows_loaded:,}")

    print("\nDone. Verify in Snowflake:")
    print("  -- Total rows and last load time")
    print("  SELECT COUNT(*), MAX(ingestion_timestamp) FROM RAW.SOCRATA_311;")
    print()
    print("  -- Rows per load date")
    print("  SELECT ingestion_timestamp::DATE AS load_date, COUNT(*) AS rows_loaded")
    print("  FROM RAW.SOCRATA_311 GROUP BY 1 ORDER BY 1 DESC;")


if __name__ == "__main__":
    main()
