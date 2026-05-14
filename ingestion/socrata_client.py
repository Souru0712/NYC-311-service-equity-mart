from datetime import datetime, timedelta, timezone
from typing import Iterator
import logging

import pandas as pd
from sodapy import Socrata

logger = logging.getLogger(__name__)


def get_watermark(sf_conn, table: str = "RAW.SOCRATA_311") -> datetime:
    """Return MAX(resolution_action_updated_date) from Snowflake, minus 48h safety buffer.
    Falls back to now() - 48h if the table is empty or doesn't exist."""
    try:
        cursor = sf_conn.cursor()
        cursor.execute(f"SELECT MAX(resolution_action_updated_date) FROM {table}")
        row = cursor.fetchone()
        max_ts = row[0] if row and row[0] else None
        cursor.close()
    except Exception:
        max_ts = None

    if max_ts is None:
        watermark = datetime.now(timezone.utc) - timedelta(hours=48)
        logger.info("Table empty or missing — watermark set to %s", watermark)
    else:
        if hasattr(max_ts, "tzinfo") and max_ts.tzinfo is None:
            max_ts = max_ts.replace(tzinfo=timezone.utc)
        watermark = max_ts - timedelta(hours=48)
        logger.info("Watermark from table MAX: %s", watermark)

    return watermark


def fetch_incremental(
    app_token: str,
    dataset_id: str,
    watermark: datetime,
    batch_size: int = 50_000,
) -> Iterator[list[dict]]:
    """Yield batches of 311 records updated at or after watermark.
    Paginates via $offset until a batch returns fewer rows than batch_size."""
    client = Socrata("data.cityofnewyork.us", app_token, timeout=60)
    where = f"resolution_action_updated_date >= '{watermark.strftime('%Y-%m-%dT%H:%M:%S')}'"
    offset = 0

    while True:
        batch = client.get(
            dataset_id,
            where=where,
            order="resolution_action_updated_date ASC",
            limit=batch_size,
            offset=offset,
        )
        if not batch:
            break

        logger.info("Fetched %d records at offset %d", len(batch), offset)
        yield batch

        if len(batch) < batch_size:
            break
        offset += batch_size

    client.close()


def records_to_dataframe(records: list[dict]) -> pd.DataFrame:
    """Coerce Socrata JSON records to a typed DataFrame.
    Dates are kept as ISO strings so Snowflake stores them as VARCHAR exactly as
    received — dbt staging handles casting via TO_TIMESTAMP_NTZ().
    Converting to pandas datetime here causes pyarrow to write int64 nanoseconds,
    which land in Snowflake as large integers instead of readable date strings."""
    df = pd.DataFrame(records)

    for col in ["latitude", "longitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["ingestion_timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
    return df
