"""One-time historical backfill. Run manually:
    python -m ingestion.backfill

Loads all 311 records month-by-month from 2010-01 through the current month.
Idempotent: each month writes to a fixed S3 key; re-running overwrites it and
re-runs the Snowflake COPY (Snowflake deduplicates via the staging QUALIFY window).
"""
import logging
from calendar import monthrange
from datetime import datetime, timezone

import pandas as pd

from ingestion.config import Config
from ingestion.socrata_client import records_to_dataframe
from ingestion.tract_geometry import download_tract_geojson, assign_tract_geoid
from ingestion.s3_writer import write_parquet_to_s3
from ingestion.snowflake_loader import get_connection, copy_311_from_s3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def backfill_month(
    year: int,
    month: int,
    cfg: Config,
    tracts_gdf,
    sf_conn,
    batch_size: int = 50_000,
) -> None:
    """Fetch all 311 records created in a single calendar month and load to Snowflake."""
    from sodapy import Socrata

    start = f"{year}-{month:02d}-01T00:00:00"
    last_day = monthrange(year, month)[1]
    end = f"{year}-{month:02d}-{last_day:02d}T23:59:59"
    where = f"created_date >= '{start}' AND created_date <= '{end}'"

    client = Socrata("data.cityofnewyork.us", cfg.socrata_app_token, timeout=120)
    all_records: list[dict] = []
    offset = 0

    while True:
        batch = client.get(
            cfg.socrata_dataset_id,
            where=where,
            order="created_date ASC",
            limit=batch_size,
            offset=offset,
        )
        if not batch:
            break
        all_records.extend(batch)
        logger.info("%d-%02d: fetched %d records (total %d)", year, month, len(batch), len(all_records))
        if len(batch) < batch_size:
            break
        offset += batch_size

    client.close()

    if not all_records:
        logger.info("%d-%02d: no records found, skipping", year, month)
        return

    df = records_to_dataframe(all_records)
    df = assign_tract_geoid(df, tracts_gdf)

    run_date = f"{year}-{month:02d}-01"
    s3_uri = write_parquet_to_s3(
        df,
        bucket=cfg.s3_bucket,
        prefix="raw/socrata_311",
        run_date=run_date,
        aws_access_key=cfg.aws_access_key,
        aws_secret_key=cfg.aws_secret_key,
        aws_region=cfg.aws_region,
    )
    copy_311_from_s3(sf_conn, s3_uri, cfg.snowflake_stage)
    logger.info("%d-%02d: done (%d rows)", year, month, len(df))


def run_full_backfill(start_year: int = 2020) -> None:
    # Socrata dataset erm2-nwe9 confirmed to have no records before 2020.
    # Older data was either not migrated or lives in a different dataset ID.
    cfg = Config()
    sf_conn = get_connection(cfg)
    tracts_gdf = download_tract_geojson(cfg.tract_geojson_cache)

    now = datetime.now(timezone.utc)
    end_year, end_month = now.year, now.month

    year, month = start_year, 1
    while (year, month) <= (end_year, end_month):
        try:
            backfill_month(year, month, cfg, tracts_gdf, sf_conn)
        except Exception as e:
            logger.error("Failed %d-%02d: %s", year, month, e)
            raise

        month += 1
        if month > 12:
            month = 1
            year += 1

    sf_conn.close()
    logger.info("Backfill complete")


if __name__ == "__main__":
    run_full_backfill()
