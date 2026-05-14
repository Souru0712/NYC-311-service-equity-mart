"""Daily incremental pipeline: Socrata → S3 → Snowflake → dbt → Great Expectations."""
import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.utils.trigger_rule import TriggerRule

DBT_DIR = os.environ.get("DBT_PROJECT_DIR", "/opt/airflow/dbt")
GE_DIR = os.environ.get("GE_PROJECT_DIR", "/opt/airflow/great_expectations")

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email": ["oscarlam84@gmail.com"],
}


def _get_watermark(**context):
    from ingestion.config import Config
    from ingestion.snowflake_loader import get_connection, create_raw_311_table
    from ingestion.socrata_client import get_watermark
    cfg = Config()
    sf_conn = get_connection(cfg)
    create_raw_311_table(sf_conn)
    wm = get_watermark(sf_conn)
    sf_conn.close()
    context["task_instance"].xcom_push(key="watermark", value=wm.isoformat())


def _fetch_311(**context):
    import pandas as pd
    from datetime import datetime
    from ingestion.config import Config
    from ingestion.socrata_client import fetch_incremental, records_to_dataframe
    cfg = Config()
    wm_str = context["task_instance"].xcom_pull(task_ids="get_watermark", key="watermark")
    watermark = datetime.fromisoformat(wm_str)
    frames = []
    for batch in fetch_incremental(cfg.socrata_app_token, cfg.socrata_dataset_id, watermark):
        frames.append(records_to_dataframe(batch))
    if not frames:
        raise ValueError("No records fetched — possible Socrata API issue or empty window")
    df = pd.concat(frames, ignore_index=True)
    tmp_path = "/tmp/311_incremental.parquet"
    df.to_parquet(tmp_path, index=False)
    context["task_instance"].xcom_push(key="tmp_path", value=tmp_path)


def _sjoin_tract(**context):
    import pandas as pd
    from ingestion.config import Config
    from ingestion.tract_geometry import download_tract_geojson, assign_tract_geoid
    cfg = Config()
    tmp_path = context["task_instance"].xcom_pull(task_ids="fetch_311_from_socrata", key="tmp_path")
    df = pd.read_parquet(tmp_path)
    tracts_gdf = download_tract_geojson(cfg.tract_geojson_cache)
    df = assign_tract_geoid(df, tracts_gdf)
    df.to_parquet(tmp_path, index=False)


def _write_to_s3(**context):
    import pandas as pd
    from ingestion.config import Config
    from ingestion.s3_writer import write_parquet_to_s3
    cfg = Config()
    tmp_path = context["task_instance"].xcom_pull(task_ids="fetch_311_from_socrata", key="tmp_path")
    df = pd.read_parquet(tmp_path)
    s3_uri = write_parquet_to_s3(
        df,
        bucket=cfg.s3_bucket,
        prefix="raw/socrata_311",
        run_date=context["ds"],
        aws_access_key=cfg.aws_access_key,
        aws_secret_key=cfg.aws_secret_key,
        aws_region=cfg.aws_region,
    )
    context["task_instance"].xcom_push(key="s3_uri", value=s3_uri)


def _validate_ge(checkpoint_name: str, **context):
    import great_expectations as ge
    from urllib.parse import quote_plus
    from ingestion.config import Config
    cfg = Config()
    ctx = ge.get_context(context_root_dir=GE_DIR)
    ctx.add_datasource(
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
                    "RAW.SOCRATA_311":          {"schema_name": "RAW",     "table_name": "SOCRATA_311"},
                    "STAGING.STG_311_REQUESTS": {"schema_name": "STAGING", "table_name": "STG_311_REQUESTS"},
                    "MARTS.FCT_EQUITY_SPLITS":  {"schema_name": "MARTS",   "table_name": "FCT_EQUITY_SPLITS"},
                    "MARTS.DIM_TRACT":          {"schema_name": "MARTS",   "table_name": "DIM_TRACT"},
                },
            }
        },
    )
    result = ctx.run_checkpoint(checkpoint_name=checkpoint_name)
    if not result["success"]:
        raise ValueError(f"Great Expectations checkpoint '{checkpoint_name}' FAILED")


def _copy_into_snowflake(**context):
    from ingestion.config import Config
    from ingestion.snowflake_loader import get_connection, copy_311_from_s3
    cfg = Config()
    s3_uri = context["task_instance"].xcom_pull(task_ids="write_parquet_to_s3", key="s3_uri")
    sf_conn = get_connection(cfg)
    copy_311_from_s3(sf_conn, s3_uri, cfg.snowflake_stage)
    sf_conn.close()


def _notify_failure(**context):
    import logging
    logging.error("DAG '%s' run %s had task failures.", context["dag"].dag_id, context["run_id"])


with DAG(
    dag_id="nyc_311_daily_incremental",
    default_args=default_args,
    schedule_interval="0 6 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["311", "equity", "incremental"],
) as dag:

    get_watermark = PythonOperator(task_id="get_watermark", python_callable=_get_watermark)
    fetch_311 = PythonOperator(task_id="fetch_311_from_socrata", python_callable=_fetch_311)
    sjoin_tract = PythonOperator(task_id="sjoin_tract_geoid", python_callable=_sjoin_tract)
    write_s3 = PythonOperator(task_id="write_parquet_to_s3", python_callable=_write_to_s3)

    validate_raw = PythonOperator(
        task_id="validate_raw_ge",
        python_callable=_validate_ge,
        op_kwargs={"checkpoint_name": "raw_311_socrata_checkpoint"},
    )

    copy_snowflake = PythonOperator(task_id="copy_into_snowflake", python_callable=_copy_into_snowflake)

    dbt_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=f"cd {DBT_DIR} && dbt run --select staging --profiles-dir ~/.dbt",
    )

    validate_staging = PythonOperator(
        task_id="validate_staging_ge",
        python_callable=_validate_ge,
        op_kwargs={"checkpoint_name": "staging_311_typed_checkpoint"},
    )

    dbt_intermediate = BashOperator(
        task_id="dbt_run_intermediate",
        bash_command=f"cd {DBT_DIR} && dbt run --select intermediate --profiles-dir ~/.dbt",
    )

    dbt_marts = BashOperator(
        task_id="dbt_run_marts",
        bash_command=f"cd {DBT_DIR} && dbt run --select marts --profiles-dir ~/.dbt",
    )

    validate_equity = PythonOperator(
        task_id="validate_fct_equity_splits_ge",
        python_callable=_validate_ge,
        op_kwargs={"checkpoint_name": "fct_equity_splits_checkpoint"},
    )

    validate_dim = PythonOperator(
        task_id="validate_dim_tract_ge",
        python_callable=_validate_ge,
        op_kwargs={"checkpoint_name": "dim_tract_checkpoint"},
    )

    dbt_test = BashOperator(
        task_id="dbt_test_all",
        bash_command=f"cd {DBT_DIR} && dbt test --profiles-dir ~/.dbt",
    )

    notify_failure = PythonOperator(
        task_id="notify_on_failure",
        python_callable=_notify_failure,
        trigger_rule=TriggerRule.ONE_FAILED,
    )

    get_watermark >> fetch_311 >> sjoin_tract >> write_s3 >> validate_raw
    validate_raw >> copy_snowflake >> dbt_staging >> validate_staging
    validate_staging >> dbt_intermediate >> dbt_marts
    dbt_marts >> [validate_equity, validate_dim]
    [validate_equity, validate_dim] >> dbt_test >> notify_failure
