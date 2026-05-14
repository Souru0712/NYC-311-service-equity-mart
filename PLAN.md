# NYC 311 Service Equity Mart — Project Plan

## The Question This Answers

If you live in Brownsville vs the Upper East Side, does the city respond to your 311 calls at the same speed?

## Context

311 response times in NYC vary significantly by borough, complaint type, and neighborhood income. There is no public-facing tool that lets residents compare service levels across census tracts or see whether lower-income neighborhoods receive systematically slower responses.

This project builds an end-to-end pipeline that ingests NYC 311 data incrementally from the Socrata API, stores it in S3 and Snowflake, models it with dbt to compute response-time percentiles joined to census tract demographics, validates quality with Great Expectations, and exposes equity insights through a Streamlit dashboard.

---

## Architecture

```
Socrata API → Airflow → S3 → Snowflake → dbt (staging → intermediate → marts) → Streamlit
```

---

## 1. Project Structure

```
nyc-311-service-equity-mart/
├── .env.example
├── .gitignore
├── requirements.txt
├── docker-compose.yml              # Local Airflow (webserver + scheduler + postgres)
├── PLAN.md                         # This file
├── README.md
│
├── ingestion/
│   ├── config.py                   # Reads .env; typed Config dataclass
│   ├── socrata_client.py           # Paginated Socrata fetch + watermark logic
│   ├── acs_client.py               # Census ACS annual pull
│   ├── tract_geometry.py           # Download NYC tract GeoJSON; geopandas sjoin
│   ├── s3_writer.py                # Write Parquet to S3
│   ├── snowflake_loader.py         # COPY INTO from S3 external stage
│   └── backfill.py                 # One-time month-chunked historical load
│
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml.example
│   ├── packages.yml                # dbt-utils
│   ├── models/
│   │   ├── staging/
│   │   │   ├── _sources.yml
│   │   │   ├── _staging.yml
│   │   │   ├── stg_311_requests.sql
│   │   │   └── stg_acs_demographics.sql
│   │   ├── intermediate/
│   │   │   ├── _intermediate.yml
│   │   │   └── int_311_with_response_time.sql
│   │   └── marts/
│   │       ├── _marts.yml
│   │       ├── dim_tract.sql
│   │       ├── fct_request_response_time.sql
│   │       └── fct_equity_splits.sql
│   ├── tests/
│   │   └── assert_percentile_ordering.sql
│   └── macros/
│       └── generate_schema_name.sql
│
├── great_expectations/
│   ├── great_expectations.yml
│   ├── checkpoints/
│   │   ├── raw_311_socrata_checkpoint.yml
│   │   ├── staging_311_typed_checkpoint.yml
│   │   ├── fct_equity_splits_checkpoint.yml
│   │   └── dim_tract_checkpoint.yml
│   └── expectations/
│       ├── raw_311_socrata.json
│       ├── staging_311_typed.json
│       ├── fct_equity_splits.json
│       └── dim_tract.json
│
├── airflow/
│   └── dags/
│       ├── dag_311_daily_incremental.py
│       ├── dag_311_backfill.py
│       └── dag_acs_annual.py
│
└── dashboard/
    ├── app.py
    ├── pages/
    │   ├── 01_borough_map.py
    │   ├── 02_equity_by_income.py
    │   ├── 03_complaint_breakdown.py
    │   └── 04_key_findings.py
    └── utils/
        ├── snowflake_conn.py
        └── chart_helpers.py
```

---

## 2. Data Sources

| Source | What | How |
|---|---|---|
| [NYC 311 Service Requests](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9) | ~35M rows, updated daily | Socrata API (`erm2-nwe9`) |
| US Census ACS 5-Year | Tract-level demographics | Census API, annual |
| NYC Census Tract Boundaries | 2020 tract polygons (GeoJSON) | NYC Open Data |

---

## 3. Ingestion Layer

### Socrata Pull (`ingestion/socrata_client.py`)

- **Dataset ID**: `erm2-nwe9`
- **Cursor field**: `resolution_action_updated_date` — not `created_date`. Using `created_date` would miss response-time updates for records closed days/weeks after creation. The cursor field captures every mutation (status change, closure, reassignment).
- **Watermark**: `MAX(resolution_action_updated_date)` from `RAW.SOCRATA_311` minus 48-hour buffer. Falls back to `now() - 48h` on first run.
- **Pagination**: `$limit=50000`, `$offset` loop, stop when batch < 50,000 rows.
- **Daily volume**: ~5,000–15,000 records/day in incremental mode.

### Spatial Join (`ingestion/tract_geometry.py`)

- Downloads NYC 2020 Census Tract GeoJSON; cached at `ingestion/data/nyc_tracts.geojson`.
- `geopandas.sjoin` point-in-polygon assigns `tract_geoid` to each record using `latitude`/`longitude`.
- Rows without coordinates (~5%) get `NULL tract_geoid`; they are excluded by the mart's `INNER JOIN`.
- The join runs in Python before the Snowflake load — avoids Snowflake `GEOGRAPHY` types.

### S3 Layout

```
s3://{BUCKET}/
  raw/
    socrata_311/
      ingestion_date=YYYY-MM-DD/
        part-0001.parquet        ← one file per daily run
    acs_demographics/
      year=YYYY/
        acs_tract_nyc.parquet
```

Partition key is `ingestion_date` (run date), not `created_date` — avoids thousands of tiny partitions during backfill.

### Snowflake Load

- `RAW.SOCRATA_311` — append-only. All columns VARCHAR except `latitude FLOAT`, `longitude FLOAT`, `ingestion_timestamp TIMESTAMP_NTZ`.
- Load via `COPY INTO` from S3 external stage `RAW.S3_STAGE`. `PURGE=FALSE` keeps files as backup.
- Deduplication is handled downstream in `stg_311_requests` via `QUALIFY`.

### Backfill

```bash
python -m ingestion.backfill   # run once manually, not via Airflow
```

Iterates month-by-month 2020–present. ~75 months × ~200K avg rows. Expect 2–3 hours. Idempotent — re-running any month overwrites the same S3 key. Note: Socrata dataset `erm2-nwe9` confirmed to have no records before 2020.

---

## 4. dbt Layer

### Materializations

| Layer | Strategy | Why |
|---|---|---|
| `staging` | `view` | No storage cost; always reflects latest raw |
| `intermediate` | `incremental` (merge) | Avoids reprocessing 35M rows; updates response_time_hours as records close |
| `marts` | `table` | Pre-aggregated for fast dashboard queries |

### Data Lineage

```
stg_311_requests ──────────────────────────────► int_311_with_response_time (merge)
stg_acs_demographics ──► dim_tract (table)              │
                              │                          ▼
                              └──────────────► fct_request_response_time (table)
                                                         │
                                                         ▼
                                               fct_equity_splits (table)
```

### Staging

**`stg_311_requests`** — `RAW.SOCRATA_311`
- Rename/cast all columns; `UPPER(TRIM(...))` on strings; dates to `TIMESTAMP_NTZ`
- `QUALIFY ROW_NUMBER() OVER (PARTITION BY unique_key ORDER BY updated_at DESC NULLS LAST) = 1` — deduplicates raw append-only table

**`stg_acs_demographics`** — `RAW.ACS_DEMOGRAPHICS`
- Casts B19013, B01003, B17001, B03002 estimates to `INTEGER`
- Replaces Census sentinel value `-666666666` with `NULL`

### Intermediate

**`int_311_with_response_time`** — incremental merge on `unique_key`
- Computes `response_time_hours = DATEDIFF('hour', created_at, closed_at)`
- Incremental filter: `updated_at >= MAX(updated_at) - 48h` — catches records that closed days after creation
- `incremental_strategy='merge'` — updates existing rows when a previously-open record closes

### Marts (Kimball-style)

**`dim_tract`** — dimension, full rebuild
- One row per NYC census tract
- `income_quintile = NTILE(5) OVER (ORDER BY median_household_income)` — 1 = lowest income, 5 = highest
- Includes `pct_below_poverty`, racial/ethnic breakdowns

**`fct_request_response_time`** — atomic fact, full rebuild
- Grain: 1 row per closed 311 request with a matched census tract
- Columns: `unique_key`, `created_at`, `closed_at`, `request_month`, `complaint_type`, `borough`, `tract_geoid`, `response_time_hours`
- `INNER JOIN dim_tract` drops ~3% of requests with unmatched coordinates

**`fct_equity_splits`** — aggregated fact, full rebuild
- Grain: `complaint_type × tract × month`
- Columns: `p50_hours`, `p75_hours`, `p90_hours`, `equity_score`, `request_count`, `income_quintile`
- `equity_score = tract p90 / city-wide p90` for the same complaint type and month
  - `1.0` = on par with city average
  - `> 1.0` = slower than average
  - `2.5` = 2.5× longer wait than city median

**Custom test `assert_percentile_ordering.sql`** — fails if any row has `p50 > p75` or `p75 > p90`.

---

## 5. Great Expectations Suites

| Suite | Triggered After | Key Checks |
|---|---|---|
| `raw_311_socrata` | Snowflake COPY INTO | Schema match, `unique_key` not null, lat/lon in NYC bbox, row count ≥ 1 |
| `staging_311_typed` | `dbt run --select staging` | Correct types, `closed_at > created_at`, no null boroughs |
| `fct_equity_splits` | `dbt run --select marts` | p50/p75/p90 not null, equity_score in (0.01, 100), income_quintile in {1–5}, row count ≥ 10,000 |
| `dim_tract` | `dbt run --select marts` | `tract_geoid` unique, row count in (2100, 2300), pct_below_poverty in (0, 100) |

Any checkpoint failure halts the Airflow DAG at that stage.

---

## 6. Airflow DAGs

### `dag_311_daily_incremental` — `0 6 * * *`

```
get_watermark
    └─► fetch_311_from_socrata
            └─► sjoin_tract_geoid
                    └─► write_parquet_to_s3
                            └─► validate_raw_ge
                                    └─► copy_into_snowflake
                                            └─► dbt_run_staging
                                                    └─► validate_staging_ge
                                                            └─► dbt_run_intermediate
                                                                    └─► dbt_run_marts
                                                                            ├─► validate_fct_equity_splits_ge
                                                                            └─► validate_dim_tract_ge
                                                                                    └─► dbt_test_all
                                                                                            └─► notify_on_failure
```

- `catchup=False` — no replays on first deploy
- `max_active_runs=1` — prevents watermark conflicts
- `retries=2`, `retry_delay=5min`

### `dag_311_backfill` — manual only

```bash
airflow dags trigger dag_311_backfill --conf '{"year": 2022, "month": 6}'
```

### `dag_acs_annual` — `0 8 1 1 *` (Jan 1)

Full replace of `RAW.ACS_DEMOGRAPHICS` (~2,200 rows). Rebuilds `dim_tract`.

---

## 7. Streamlit Dashboard

| Page | What It Shows |
|---|---|
| `01_borough_map` | Choropleth: equity score by tract, filtered by complaint type + borough |
| `02_equity_by_income` | Bar + scatter: income quintile vs avg equity score and P90 response time |
| `03_complaint_breakdown` | Heatmap: top 20 complaint types × borough, togglable metric |
| `04_key_findings` | Rodent gap %, heat complaint borough spread ×, equity trend over time |

Snowflake connection via `@st.cache_resource`. Queries cached for 1 hour via `@st.cache_data(ttl=3600)`. Secrets in `dashboard/.streamlit/secrets.toml` (gitignored).

---

## 8. Config & Secrets Pattern

| Secret | Where |
|---|---|
| All pipeline secrets | `.env` (copy from `.env.example`) |
| dbt Snowflake credentials | `~/.dbt/profiles.yml` (copy from `dbt/profiles.yml.example`) |
| Streamlit Snowflake credentials | `dashboard/.streamlit/secrets.toml` (copy from `secrets.toml.example`) |
| Airflow connections | `docker-compose.yml` env vars (`AIRFLOW_CONN_SNOWFLAKE_DEFAULT`, `AIRFLOW_CONN_AWS_DEFAULT`) |

**Never import `Config()` at Airflow DAG module level.** Instantiate inside each task callable — prevents scheduler parse failures when env vars are absent.

---

## 9. Incremental Strategy

| Layer | Mechanism | Effect |
|---|---|---|
| Socrata pull | Watermark on `resolution_action_updated_date` - 48h | Fetches only ~5K–15K rows/day instead of 35M |
| Snowflake raw | Append-only | Cheap writes; no dedup overhead at load time |
| dbt staging | `QUALIFY ROW_NUMBER() ... = 1` | Surfaces only the latest version of each record |
| dbt intermediate | `incremental_strategy='merge'`, `unique_key='unique_key'` | Backfills `response_time_hours` when records close after creation |
| dbt marts | Full table rebuild | ~30s; aggregates from pre-filtered intermediate, not raw |

---

## 10. Verification Queries

```sql
-- Ingestion health
SELECT COUNT(*), MAX(ingestion_timestamp) FROM RAW.SOCRATA_311;
-- Should grow daily; timestamp = today

-- Incremental correctness
SELECT unique_key, created_at, closed_at, response_time_hours
FROM INTERMEDIATE.INT_311_WITH_RESPONSE_TIME
WHERE closed_at IS NOT NULL
ORDER BY closed_at DESC
LIMIT 10;

-- Equity score sanity (all 1.0 = bug in city_p90 join)
SELECT complaint_type, AVG(equity_score), STDDEV(equity_score)
FROM MARTS.FCT_EQUITY_SPLITS
GROUP BY 1 ORDER BY 2 DESC;

-- Demographic coverage
SELECT COUNT(DISTINCT tract_geoid) FROM MARTS.DIM_TRACT;
-- Expected: ~2168

-- Key finding: rodent gap
SELECT
    income_quintile,
    AVG(p50_hours) AS median_hrs,
    SUM(request_count) AS n
FROM MARTS.FCT_EQUITY_SPLITS
WHERE UPPER(complaint_type) LIKE '%RODENT%'
GROUP BY 1 ORDER BY 1;
```

---

## 11. Key Design Decisions

| Decision | Rationale |
|---|---|
| Cursor = `resolution_action_updated_date` | Captures closures and status changes; `created_date` alone misses response-time updates |
| Spatial join in Python, not Snowflake | Avoids Snowflake GEOGRAPHY complexity for beginners; cached GeoJSON means one download |
| Backfill runs outside Airflow | Prevents DAG timeouts; 4–6 hours for 35M rows is too long for a single task |
| `dim_tract` as a mart, not just staging | `NTILE(5)` needs the full NYC dataset to assign quintiles correctly — can't be done per-batch |
| `fct_equity_splits` full rebuild | Percentile aggregations don't compose incrementally; ~30s on pre-filtered data is fast enough |
