from dataclasses import dataclass, field
from dotenv import load_dotenv
import os

load_dotenv()


@dataclass
class Config:
    socrata_app_token: str = field(default_factory=lambda: os.environ["SOCRATA_APP_TOKEN"])
    socrata_dataset_id: str = field(default_factory=lambda: os.getenv("SOCRATA_DATASET_ID") or "erm2-nwe9")

    aws_access_key: str = field(default_factory=lambda: os.environ["AWS_ACCESS_KEY_ID"])
    aws_secret_key: str = field(default_factory=lambda: os.environ["AWS_SECRET_ACCESS_KEY"])
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    s3_bucket: str = field(default_factory=lambda: os.environ["S3_BUCKET"])

    snowflake_account: str = field(default_factory=lambda: os.environ["SNOWFLAKE_ACCOUNT"])
    snowflake_user: str = field(default_factory=lambda: os.environ["SNOWFLAKE_USER"])
    snowflake_password: str = field(default_factory=lambda: os.environ["SNOWFLAKE_PASSWORD"])
    snowflake_warehouse: str = field(default_factory=lambda: os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"))
    snowflake_database: str = field(default_factory=lambda: os.getenv("SNOWFLAKE_DATABASE", "NYC_311"))
    snowflake_role: str = field(default_factory=lambda: os.getenv("SNOWFLAKE_ROLE", "TRANSFORMER"))

    # Only required by load_acs.py / acs_annual.yml — not needed for 311 ingestion
    census_api_key: str | None = field(default_factory=lambda: os.getenv("CENSUS_API_KEY"))

    snowflake_stage: str = "RAW.S3_STAGE"
    snowflake_raw_table: str = "RAW.SOCRATA_311"
    snowflake_acs_table: str = "RAW.ACS_DEMOGRAPHICS"

    tract_geojson_cache: str = "ingestion/data/nyc_tracts.geojson"
