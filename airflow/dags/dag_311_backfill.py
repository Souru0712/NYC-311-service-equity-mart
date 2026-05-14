"""Manual backfill DAG. Trigger with:
    airflow dags trigger dag_311_backfill --conf '{"year": 2022, "month": 6}'
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "data-eng",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "email_on_failure": True,
    "email": ["oscarlam84@gmail.com"],
}


def _backfill_month_fetch(**context):
    import pandas as pd
    from calendar import monthrange
    from sodapy import Socrata
    from ingestion.config import Config
    from ingestion.socrata_client import records_to_dataframe
    from ingestion.tract_geometry import download_tract_geojson, assign_tract_geoid

    params = context["params"]
    year = int(params["year"])
    month = int(params["month"])

    cfg = Config()
    last_day = monthrange(year, month)[1]
    where = (
        f"created_date >= '{year}-{month:02d}-01T00:00:00' "
        f"AND created_date <= '{year}-{month:02d}-{last_day:02d}T23:59:59'"
    )

    client = Socrata("data.cityofnewyork.us", cfg.socrata_app_token, timeout=120)
    all_records, offset = [], 0
    while True:
        batch = client.get(
            cfg.socrata_dataset_id,
            where=where,
            order="created_date ASC",
            limit=50_000,
            offset=offset,
        )
        if not batch:
            break
        all_records.extend(batch)
        if len(batch) < 50_000:
            break
        offset += 50_000
    client.close()

    if not all_records:
        raise ValueError(f"No records found for {year}-{month:02d}")

    df = records_to_dataframe(all_records)
    tracts_gdf = download_tract_geojson(cfg.tract_geojson_cache)
    df = assign_tract_geoid(df, tracts_gdf)

    tmp_path = f"/tmp/311_backfill_{year}_{month:02d}.parquet"
    df.to_parquet(tmp_path, index=False)
    context["task_instance"].xcom_push(key="tmp_path", value=tmp_path)
    context["task_instance"].xcom_push(key="run_date", value=f"{year}-{month:02d}-01")


def _copy_backfill_to_snowflake(**context):
    import pandas as pd
    from ingestion.config import Config
    from ingestion.s3_writer import write_parquet_to_s3
    from ingestion.snowflake_loader import get_connection, copy_311_from_s3

    cfg = Config()
    tmp_path = context["task_instance"].xcom_pull(task_ids="backfill_month_fetch", key="tmp_path")
    run_date = context["task_instance"].xcom_pull(task_ids="backfill_month_fetch", key="run_date")

    df = pd.read_parquet(tmp_path)
    s3_uri = write_parquet_to_s3(
        df,
        bucket=cfg.s3_bucket,
        prefix="raw/socrata_311",
        run_date=run_date,
        aws_access_key=cfg.aws_access_key,
        aws_secret_key=cfg.aws_secret_key,
        aws_region=cfg.aws_region,
    )
    sf_conn = get_connection(cfg)
    copy_311_from_s3(sf_conn, s3_uri, cfg.snowflake_stage)
    sf_conn.close()


def _validate_raw_ge(**context):
    import os
    import great_expectations as ge
    from urllib.parse import quote_plus
    from ingestion.config import Config
    cfg = Config()
    ge_ctx = ge.get_context(
        context_root_dir=os.environ.get("GE_PROJECT_DIR", "/opt/airflow/great_expectations")
    )
    ge_ctx.add_datasource(
        name="snowflake_nyc311",
        class_name="Datasource",
        execution_engine={
            "class_name": "SqlAlchemyExecutionEngine",
            "connection_string": (
                f"snowflake://{cfg.snowflake_user}:{quote_plus(cfg.snowflake_password)}"
                f"@{cfg.snowflake_account}/{cfg.snowflake_database}/RAW"
                f"?warehouse={cfg.snowflake_warehouse}&role={cfg.snowflake_role}"
            ),
        },
        data_connectors={
            "default_configured_data_connector_name": {
                "class_name": "ConfiguredAssetSqlDataConnector",
                "assets": {
                    "RAW.SOCRATA_311": {"schema_name": "RAW", "table_name": "SOCRATA_311"},
                },
            }
        },
    )
    result = ge_ctx.run_checkpoint(checkpoint_name="raw_311_socrata_checkpoint")
    if not result["success"]:
        raise ValueError("GE raw checkpoint FAILED for backfill run")


with DAG(
    dag_id="dag_311_backfill",
    default_args=default_args,
    schedule_interval=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    params={"year": 2024, "month": 1},
    tags=["311", "backfill"],
) as dag:

    fetch = PythonOperator(
        task_id="backfill_month_fetch",
        python_callable=_backfill_month_fetch,
    )

    load = PythonOperator(
        task_id="copy_into_snowflake_backfill",
        python_callable=_copy_backfill_to_snowflake,
    )

    validate = PythonOperator(
        task_id="validate_raw_ge_backfill",
        python_callable=_validate_raw_ge,
    )

    fetch >> load >> validate
