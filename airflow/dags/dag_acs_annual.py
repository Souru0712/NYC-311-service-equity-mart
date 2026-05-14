"""Annual ACS demographics refresh. Runs Jan 1 each year.
Full replace — ACS is ~2,200 rows so incremental is not needed."""
import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

DBT_DIR = os.environ.get("DBT_PROJECT_DIR", "/opt/airflow/dbt")
GE_DIR = os.environ.get("GE_PROJECT_DIR", "/opt/airflow/great_expectations")

default_args = {
    "owner": "data-eng",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "email_on_failure": True,
    "email": ["oscarlam84@gmail.com"],
}


def _fetch_acs(**context):
    import pandas as pd
    from ingestion.config import Config
    from ingestion.acs_client import fetch_nyc_acs
    from ingestion.s3_writer import write_parquet_to_s3
    cfg = Config()
    # ACS releases each December with ~13-month lag (2024 vintage → Dec 2025).
    # Cap at year-2 when running in January before the prior year's release is out.
    vintage_year = context["execution_date"].year - 2
    df = fetch_nyc_acs(api_key=cfg.census_api_key, vintage_year=vintage_year)
    tmp_path = f"/tmp/acs_{vintage_year}.parquet"
    df.to_parquet(tmp_path, index=False)
    context["task_instance"].xcom_push(key="tmp_path", value=tmp_path)
    s3_uri = write_parquet_to_s3(
        df,
        bucket=cfg.s3_bucket,
        prefix="raw/acs_demographics",
        run_date=f"year={vintage_year}",
        aws_access_key=cfg.aws_access_key,
        aws_secret_key=cfg.aws_secret_key,
        aws_region=cfg.aws_region,
    )
    context["task_instance"].xcom_push(key="s3_uri", value=s3_uri)


def _load_acs_to_snowflake(**context):
    import pandas as pd
    from ingestion.config import Config
    from ingestion.snowflake_loader import get_connection, create_raw_acs_table, truncate_and_load_acs
    cfg = Config()
    tmp_path = context["task_instance"].xcom_pull(task_ids="fetch_acs_demographics", key="tmp_path")
    df = pd.read_parquet(tmp_path)
    sf_conn = get_connection(cfg)
    create_raw_acs_table(sf_conn)
    truncate_and_load_acs(sf_conn, df)
    sf_conn.close()


def _validate_dim_ge(**context):
    import great_expectations as ge
    from urllib.parse import quote_plus
    from ingestion.config import Config
    cfg = Config()
    ge_ctx = ge.get_context(context_root_dir=GE_DIR)
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
                    "MARTS.DIM_TRACT": {"schema_name": "MARTS", "table_name": "DIM_TRACT"},
                },
            }
        },
    )
    result = ge_ctx.run_checkpoint(checkpoint_name="dim_tract_checkpoint")
    if not result["success"]:
        raise ValueError("GE dim_tract checkpoint FAILED")


with DAG(
    dag_id="dag_acs_annual",
    default_args=default_args,
    schedule_interval="0 8 1 1 *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["acs", "demographics", "annual"],
) as dag:

    fetch_acs = PythonOperator(task_id="fetch_acs_demographics", python_callable=_fetch_acs)
    load_acs = PythonOperator(task_id="copy_acs_into_snowflake", python_callable=_load_acs_to_snowflake)

    dbt_acs = BashOperator(
        task_id="dbt_run_acs_staging",
        bash_command=(
            f"cd {DBT_DIR} && dbt run "
            f"--select stg_acs_demographics dim_tract "
            f"--profiles-dir ~/.dbt"
        ),
    )

    validate_dim = PythonOperator(
        task_id="validate_dim_tract_ge",
        python_callable=_validate_dim_ge,
    )

    fetch_acs >> load_acs >> dbt_acs >> validate_dim
