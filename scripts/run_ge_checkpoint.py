"""
Run a Great Expectations checkpoint by name.

Usage (from project root):
    python scripts/run_ge_checkpoint.py raw_311_socrata_checkpoint
    python scripts/run_ge_checkpoint.py staging_311_typed_checkpoint
    python scripts/run_ge_checkpoint.py dim_tract_checkpoint
    python scripts/run_ge_checkpoint.py fct_equity_splits_checkpoint

Credentials are read from great_expectations/uncommitted/config_variables.yml.
"""
import os
import sys
from urllib.parse import quote_plus

import yaml

sys.path.insert(0, ".")

VALID_CHECKPOINTS = [
    "raw_311_socrata_checkpoint",
    "staging_311_typed_checkpoint",
    "dim_tract_checkpoint",
    "fct_equity_splits_checkpoint",
]

GE_ROOT = os.path.join(os.getcwd(), "great_expectations")
CONFIG_VARS_PATH = os.path.join(GE_ROOT, "uncommitted", "config_variables.yml")

# Explicit table definitions — avoids InferredAssetSqlDataConnector naming issues
CONFIGURED_ASSETS = {
    "RAW.SOCRATA_311":          {"schema_name": "RAW",      "table_name": "SOCRATA_311"},
    "STAGING.STG_311_REQUESTS": {"schema_name": "STAGING",  "table_name": "STG_311_REQUESTS"},
    "MARTS.FCT_EQUITY_SPLITS":  {"schema_name": "MARTS",    "table_name": "FCT_EQUITY_SPLITS"},
    "MARTS.DIM_TRACT":          {"schema_name": "MARTS",    "table_name": "DIM_TRACT"},
}


def load_config_vars() -> dict:
    if not os.path.exists(CONFIG_VARS_PATH):
        raise FileNotFoundError(
            f"Missing: {CONFIG_VARS_PATH}\n"
            "Fill in your Snowflake credentials there before running GE."
        )
    with open(CONFIG_VARS_PATH) as f:
        return yaml.safe_load(f)


def build_datasource_config(cfg: dict) -> dict:
    password = quote_plus(cfg["SNOWFLAKE_PASSWORD"])
    connection_string = (
        f"snowflake://{cfg['SNOWFLAKE_USER']}:{password}"
        f"@{cfg['SNOWFLAKE_ACCOUNT']}/NYC_311/RAW"
        f"?warehouse={cfg['SNOWFLAKE_WAREHOUSE']}&role={cfg['SNOWFLAKE_ROLE']}"
    )
    return {
        "name": "snowflake_nyc311",
        "class_name": "Datasource",
        "execution_engine": {
            "class_name": "SqlAlchemyExecutionEngine",
            "connection_string": connection_string,
        },
        "data_connectors": {
            "default_configured_data_connector_name": {
                "class_name": "ConfiguredAssetSqlDataConnector",
                "assets": CONFIGURED_ASSETS,
            }
        },
    }


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/run_ge_checkpoint.py <checkpoint_name>")
        print("Available checkpoints:")
        for cp in VALID_CHECKPOINTS:
            print(f"  {cp}")
        sys.exit(1)

    checkpoint_name = sys.argv[1]
    if checkpoint_name not in VALID_CHECKPOINTS:
        print(f"Unknown checkpoint: {checkpoint_name}")
        print("Available:", ", ".join(VALID_CHECKPOINTS))
        sys.exit(1)

    cfg = load_config_vars()

    import great_expectations as ge

    context = ge.get_context(context_root_dir=GE_ROOT)
    context.add_datasource(**build_datasource_config(cfg))

    print(f"Running checkpoint: {checkpoint_name} ...")
    result = context.run_checkpoint(checkpoint_name=checkpoint_name)

    if result["success"]:
        print(f"\n✓  {checkpoint_name} PASSED")
        for _, val in result.run_results.items():
            r = val["validation_result"]
            total  = r.statistics["evaluated_expectations"]
            passed = r.statistics["successful_expectations"]
            print(f"   {passed}/{total} expectations passed")
    else:
        print(f"\n✗  {checkpoint_name} FAILED")
        for _, val in result.run_results.items():
            r = val["validation_result"]
            for exp in r.results:
                if not exp.success:
                    print(f"   FAILED: {exp.expectation_config.expectation_type}")
                    print(f"     kwargs: {exp.expectation_config.kwargs}")
                    print(f"     result: {exp.result}")
        sys.exit(1)


if __name__ == "__main__":
    main()
