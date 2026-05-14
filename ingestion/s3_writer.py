import logging
from io import BytesIO

import boto3
import pandas as pd

logger = logging.getLogger(__name__)


def write_parquet_to_s3(
    df: pd.DataFrame,
    bucket: str,
    prefix: str,
    run_date: str,
    aws_access_key: str,
    aws_secret_key: str,
    aws_region: str = "us-east-1",
) -> str:
    """Write df as snappy-compressed Parquet to s3://{bucket}/{prefix}/ingestion_date={run_date}/part-0001.parquet.
    Returns the S3 URI."""
    key = f"{prefix}/ingestion_date={run_date}/part-0001.parquet"
    uri = f"s3://{bucket}/{key}"

    buffer = BytesIO()
    df.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
    buffer.seek(0)

    client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
    )
    client.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue())
    logger.info("Wrote %d rows to %s", len(df), uri)
    return uri


def write_file_to_s3(
    local_path: str,
    bucket: str,
    key: str,
    aws_access_key: str,
    aws_secret_key: str,
    aws_region: str = "us-east-1",
) -> str:
    """Upload a local file (e.g., GeoJSON) to S3. Returns the S3 URI."""
    client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
    )
    with open(local_path, "rb") as f:
        client.put_object(Bucket=bucket, Key=key, Body=f.read())

    uri = f"s3://{bucket}/{key}"
    logger.info("Uploaded %s to %s", local_path, uri)
    return uri
