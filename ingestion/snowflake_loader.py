import logging

import snowflake.connector

logger = logging.getLogger(__name__)


def get_connection(cfg) -> snowflake.connector.SnowflakeConnection:
    return snowflake.connector.connect(
        account=cfg.snowflake_account,
        user=cfg.snowflake_user,
        password=cfg.snowflake_password,
        warehouse=cfg.snowflake_warehouse,
        database=cfg.snowflake_database,
        role=cfg.snowflake_role,
    )


def create_raw_311_table(sf_conn) -> None:
    """CREATE TABLE IF NOT EXISTS RAW.SOCRATA_311.
    All columns VARCHAR except lat/lon (FLOAT) and ingestion_timestamp (TIMESTAMP_NTZ)."""
    ddl = """
    CREATE TABLE IF NOT EXISTS RAW.SOCRATA_311 (
        unique_key                         VARCHAR,
        created_date                       VARCHAR,
        closed_date                        VARCHAR,
        resolution_action_updated_date     VARCHAR,
        agency                             VARCHAR,
        agency_name                        VARCHAR,
        complaint_type                     VARCHAR,
        descriptor                         VARCHAR,
        location_type                      VARCHAR,
        incident_zip                       VARCHAR,
        incident_address                   VARCHAR,
        street_name                        VARCHAR,
        cross_street_1                     VARCHAR,
        cross_street_2                     VARCHAR,
        intersection_street_1              VARCHAR,
        intersection_street_2              VARCHAR,
        address_type                       VARCHAR,
        city                               VARCHAR,
        landmark                           VARCHAR,
        facility_type                      VARCHAR,
        status                             VARCHAR,
        due_date                           VARCHAR,
        resolution_description             VARCHAR,
        borough                            VARCHAR,
        x_coordinate_state_plane          VARCHAR,
        y_coordinate_state_plane          VARCHAR,
        open_data_channel_type             VARCHAR,
        park_facility_name                 VARCHAR,
        park_borough                       VARCHAR,
        vehicle_type                       VARCHAR,
        taxi_company_borough               VARCHAR,
        taxi_pick_up_location              VARCHAR,
        bridge_highway_name                VARCHAR,
        bridge_highway_direction           VARCHAR,
        road_ramp                          VARCHAR,
        bridge_highway_segment             VARCHAR,
        latitude                           FLOAT,
        longitude                          FLOAT,
        tract_geoid                        VARCHAR,
        ingestion_timestamp                TIMESTAMP_NTZ
    )
    """
    cursor = sf_conn.cursor()
    cursor.execute(ddl)
    cursor.close()
    logger.info("RAW.SOCRATA_311 table ready")


def create_raw_acs_table(sf_conn) -> None:
    """CREATE TABLE IF NOT EXISTS RAW.ACS_DEMOGRAPHICS."""
    ddl = """
    CREATE TABLE IF NOT EXISTS RAW.ACS_DEMOGRAPHICS (
        geo_id              VARCHAR,
        b19013_001e         FLOAT,
        b01003_001e         FLOAT,
        b17001_002e         FLOAT,
        b03002_003e         FLOAT,
        b03002_012e         FLOAT,
        b03002_004e         FLOAT,
        state               VARCHAR,
        county              VARCHAR,
        tract               VARCHAR,
        county_fips         VARCHAR,
        vintage_year        INTEGER
    )
    """
    cursor = sf_conn.cursor()
    cursor.execute(ddl)
    cursor.close()
    logger.info("RAW.ACS_DEMOGRAPHICS table ready")


def copy_311_from_s3(sf_conn, s3_uri: str, stage_name: str = "RAW.S3_STAGE") -> int:
    """COPY INTO RAW.SOCRATA_311 from a specific S3 Parquet file.
    Returns number of rows loaded."""
    # Extract the relative path within the bucket (strip s3://bucket-name/)
    key = s3_uri.split("/", 3)[-1]
    sql = f"""
    COPY INTO RAW.SOCRATA_311
    FROM @{stage_name}/{key}
    FILE_FORMAT = (TYPE = PARQUET)
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
    PURGE = FALSE
    """
    cursor = sf_conn.cursor()
    try:
        cursor.execute(sql)
        rows = cursor.fetchone()
    except Exception as e:
        msg = str(e)
        if "does not exist" in msg and "stage" in msg.lower():
            raise RuntimeError(
                f"Stage '{stage_name}' not found. "
                "Create it in Snowflake first — see README step 5."
            ) from e
        if "Insufficient privileges" in msg or "not authorized" in msg.lower():
            raise RuntimeError(
                f"Role lacks privileges to use stage '{stage_name}' or insert into RAW.SOCRATA_311. "
                "Run in Snowflake as ACCOUNTADMIN:\n"
                "  GRANT ALL ON ALL STAGES IN SCHEMA NYC_311.RAW TO ROLE TRANSFORMER;\n"
                "  GRANT ALL PRIVILEGES ON FUTURE TABLES IN SCHEMA NYC_311.RAW TO ROLE TRANSFORMER;"
            ) from e
        raise RuntimeError(f"COPY INTO failed: {msg}") from e
    finally:
        cursor.close()

    loaded = rows[3] if rows else 0
    logger.info("COPY INTO loaded %d rows from %s", loaded, s3_uri)
    return loaded


def truncate_and_load_acs(sf_conn, df) -> None:
    """Full replace of RAW.ACS_DEMOGRAPHICS (2,200 rows — no need for incremental)."""
    from snowflake.connector.pandas_tools import write_pandas

    # write_pandas quotes column names making them case-sensitive.
    # Snowflake stores unquoted identifiers as uppercase, so columns must
    # be uppercased before writing or the INSERT will fail with "invalid identifier".
    df = df.copy()
    df.columns = [c.upper() for c in df.columns]

    cursor = sf_conn.cursor()
    cursor.execute("TRUNCATE TABLE RAW.ACS_DEMOGRAPHICS")
    cursor.close()

    success, nchunks, nrows, _ = write_pandas(
        sf_conn,
        df,
        "ACS_DEMOGRAPHICS",
        schema="RAW",
        auto_create_table=False,
    )
    logger.info("Loaded %d ACS rows in %d chunks (success=%s)", nrows, nchunks, success)
