# NYC 311 Service Equity Mart

> **If you live in Brownsville vs the Upper East Side, does the city respond to your 311 calls at the same speed?**

An end-to-end data pipeline that ingests all NYC 311 service requests, joins them to census tract demographics, and surfaces response-time equity gaps in an interactive dashboard.

**Stack**: Socrata API → Airflow → S3 → Snowflake → dbt → Great Expectations → Streamlit → Groq (AI)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone & Install](#2-clone--install)
3. [Create Accounts & Credentials](#3-create-accounts--credentials)
4. [Configure Secrets](#4-configure-secrets)
5. [Set Up Snowflake](#5-set-up-snowflake)
6. [Test a Single-Day Ingestion](#6-test-a-single-day-ingestion)
7. [Run Great Expectations (Raw Suite)](#7-run-great-expectations-raw-suite)
8. [Run dbt](#8-run-dbt)
9. [Run the Historical Backfill](#9-run-the-historical-backfill)
10. [Start Airflow](#10-start-airflow)
11. [Launch the Dashboard](#11-launch-the-dashboard)
12. [AI Synthesis](#12-ai-synthesis)
13. [Project Structure](#13-project-structure)
14. [Data Model](#14-data-model)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Prerequisites

Before you begin, make sure you have these installed locally:

| Tool | Version | Install |
|---|---|---|
| Python | = 3.12 | [python.org](https://www.python.org/downloads/) |
| Git | any | [git-scm.com](https://git-scm.com/) |
| Docker Desktop | any | [docker.com](https://www.docker.com/products/docker-desktop/) |

You also need accounts for:
- **AWS** — for S3 storage (free tier is fine for dev)
- **Snowflake** — 30-day free trial at [snowflake.com](https://signup.snowflake.com/)
- **NYC Open Data (Socrata)** — free app token at [data.cityofnewyork.us](https://data.cityofnewyork.us/login)
- **US Census API** — free key at [api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html)
- **Groq** — free API key at [console.groq.com](https://console.groq.com) (AI synthesis, no credit card required)

---

## 2. Clone & Install

```bash
git clone https://github.com/your-username/nyc-311-service-equity-mart.git
cd nyc-311-service-equity-mart

#if multiple interpreters available, specify in python command (e.g. python3.12)
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

python.exe -m pip install --upgrade pip
pip install -r requirements.txt
```

Install dbt packages (run from inside the `dbt/` directory). Step 8. includes it for verification:

```bash
cd dbt
dbt deps
cd ..
```

---

## 3. Create Accounts & Credentials

### Socrata App Token
1. Go to [data.cityofnewyork.us](https://data.cityofnewyork.us/login) → sign up / log in
2. Click your profile → **Developer Settings** → **Create New App Token**
3. Copy the **App Token** (not the secret token)

### AWS S3
1. Log into [AWS Console](https://console.aws.amazon.com/) → S3 → **Create bucket**
2. Name it `nyc-311-equity-mart` (or anything unique) — region `us-east-1`
3. IAM → Create a user → attach policy `AmazonS3FullAccess` → create **Access Key**
4. Save the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`

### Snowflake
1. Sign up for a [free trial](https://signup.snowflake.com/) — choose **AWS**, region **US East (Ohio)**
2. Note your **account identifier** (format: `abc12345.us-east-1`)
3. Your login username and password are your `SNOWFLAKE_USER` / `SNOWFLAKE_PASSWORD`

### Census API Key
1. Register at [api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html)
2. Check your email — key arrives in a few minutes

---

## 4. Configure Secrets

### Pipeline secrets (`.env`)

```bash
cp .env.example .env
```

Open `.env` and fill in every value:

```bash
SOCRATA_APP_TOKEN=your_token_here
SOCRATA_DATASET_ID=erm2-nwe9

AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
S3_BUCKET=nyc-311-equity-mart

SNOWFLAKE_ACCOUNT=abc12345.us-east-1
SNOWFLAKE_USER=your_user
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=NYC_311
SNOWFLAKE_ROLE=TRANSFORMER

CENSUS_API_KEY=your_census_key
```

### dbt profile (`~/.dbt/profiles.yml`)
Open `C:\Users\oscar\.dbt\profiles.yml` (Windows) or `~/.dbt/profiles.yml` (macOS/Linux) and fill in your actual values:

```yaml
nyc_311_equity:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: "your_account_identifier"
      user: "your_snowflake_user"
      password: "your_snowflake_password"
      role: "TRANSFORMER"
      database: NYC_311
      warehouse: "COMPUTE_WH"
      schema: staging
      threads: 4
```

> This file lives outside the project in your home directory and is never committed. Do not put credentials anywhere inside the project folder.

### Streamlit secrets

**Windows (PowerShell):**
```powershell
New-Item -ItemType Directory -Force ".streamlit"
Copy-Item dashboard\.streamlit\secrets.toml.example .streamlit\secrets.toml
```

**macOS / Linux:**
```bash
mkdir -p .streamlit
cp dashboard/.streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit the file:

```toml
# Top-level keys must appear BEFORE any [section] header in TOML
GROQ_API_KEY = "gsk_..."

[snowflake]
account   = "abc12345.us-east-1"
user      = "your_user"
password  = "your_password"
warehouse = "COMPUTE_WH"
role      = "TRANSFORMER"
```

> **Never commit `.env` or `secrets.toml`** — both are in `.gitignore`.

---

## 5. Set Up Snowflake

Run these SQL statements once in the Snowflake worksheet (logged in as ACCOUNTADMIN):

```sql
-- Database and schemas
CREATE DATABASE IF NOT EXISTS NYC_311;
CREATE SCHEMA IF NOT EXISTS NYC_311.RAW;
CREATE SCHEMA IF NOT EXISTS NYC_311.STAGING;
CREATE SCHEMA IF NOT EXISTS NYC_311.INTERMEDIATE;
CREATE SCHEMA IF NOT EXISTS NYC_311.MARTS;

-- Warehouse
CREATE WAREHOUSE IF NOT EXISTS COMPUTE_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND   = 60
  AUTO_RESUME    = TRUE;

-- Role and user (optional but recommended)
CREATE USER IF NOT EXISTS user
  PASSWORD          = 'StrongPassword123!'
  DEFAULT_ROLE      = TRANSFORMER
  DEFAULT_WAREHOUSE = COMPUTE_WH
  DEFAULT_NAMESPACE = NYC_311
  MUST_CHANGE_PASSWORD = FALSE;

CREATE ROLE IF NOT EXISTS TRANSFORMER;
GRANT USAGE  ON DATABASE NYC_311                    TO ROLE TRANSFORMER;
GRANT ALL    ON ALL SCHEMAS IN DATABASE NYC_311     TO ROLE TRANSFORMER;
GRANT USAGE  ON WAREHOUSE COMPUTE_WH               TO ROLE TRANSFORMER;
GRANT ROLE TRANSFORMER TO ROLE SYSADMIN;
GRANT ROLE TRANSFORMER TO USER oscar;

-- S3 external stage (replace with your bucket name and AWS credentials)
CREATE OR REPLACE STAGE NYC_311.RAW.S3_STAGE
  URL = 's3://nyc-311-equity-mart/'
  CREDENTIALS = (
    AWS_KEY_ID     = 'your_aws_access_key'
    AWS_SECRET_KEY = 'your_aws_secret_key'
  )
  FILE_FORMAT = (TYPE = PARQUET);

-- Grant TRANSFORMER access to the stage and all current + future objects
GRANT ALL ON ALL STAGES IN SCHEMA NYC_311.RAW                    TO ROLE TRANSFORMER;
GRANT ALL PRIVILEGES ON FUTURE TABLES IN SCHEMA NYC_311.RAW      TO ROLE TRANSFORMER;
GRANT ALL PRIVILEGES ON FUTURE TABLES IN SCHEMA NYC_311.STAGING  TO ROLE TRANSFORMER;
GRANT ALL PRIVILEGES ON FUTURE TABLES IN SCHEMA NYC_311.INTERMEDIATE TO ROLE TRANSFORMER;
GRANT ALL PRIVILEGES ON FUTURE TABLES IN SCHEMA NYC_311.MARTS    TO ROLE TRANSFORMER;
GRANT ALL PRIVILEGES ON FUTURE STAGES IN SCHEMA NYC_311.RAW      TO ROLE TRANSFORMER;
GRANT ALL PRIVILEGES ON FUTURE VIEWS  IN SCHEMA NYC_311.STAGING  TO ROLE TRANSFORMER;

-- Verify
SHOW STAGES IN SCHEMA NYC_311.RAW;
SHOW GRANTS TO ROLE TRANSFORMER;
```

---

## 6. Test a Single-Day Ingestion

Before running the full pipeline, verify the end-to-end flow with one day of data:

```bash
python scripts/test_single_day.py
```

**Expected output:**
```
Fetching records updated since 2025-01-14 06:00 UTC ...
  Fetched 8,432 rows  |  columns: ['unique_key', 'created_date', 'closed_date', ...]
Downloading / loading tract boundaries ...
  tract_geoid coverage: 93.2%  (expect ~90-95%, see note below)
Writing Parquet to S3 ...
  Written to: s3://nyc-311-equity-mart/raw/socrata_311/ingestion_date=test-run/part-0001.parquet
Loading into Snowflake RAW.SOCRATA_311 ...
  Rows loaded: 8,432

Done. Verify in Snowflake:
  SELECT COUNT(*), MAX(ingestion_timestamp) FROM RAW.SOCRATA_311;
```

Verify in Snowflake:
```sql
-- Total rows and last load time (always returns 1 row — the count value is what matters)
SELECT COUNT(*), MAX(ingestion_timestamp) FROM NYC_311.RAW.SOCRATA_311;

-- Rows per load date — more useful for spotting missing or partial runs
SELECT
    ingestion_timestamp::DATE AS load_date,
    COUNT(*)                  AS rows_loaded
FROM NYC_311.RAW.SOCRATA_311
GROUP BY 1
ORDER BY 1 DESC;

-- Derive tract_geoid coverage from the raw table.
-- The percentage is logged during ingestion but not stored as a column.
-- Overall coverage:
SELECT
    COUNT(*)                                                AS total_rows,
    COUNT(tract_geoid)                                      AS with_tract,
    ROUND(100.0 * COUNT(tract_geoid) / COUNT(*), 1)        AS pct_coverage
FROM NYC_311.RAW.SOCRATA_311;
-- Expect 90–95% overall. Below 85% = spatial join issue.

-- Per-month coverage — mirrors what the backfill logs per batch:
SELECT
    DATE_TRUNC('month', TO_TIMESTAMP_NTZ(created_date))    AS month,
    COUNT(*)                                                AS total_rows,
    COUNT(tract_geoid)                                      AS with_tract,
    ROUND(100.0 * COUNT(tract_geoid) / COUNT(*), 1)        AS pct_coverage
FROM NYC_311.RAW.SOCRATA_311
WHERE created_date IS NOT NULL
GROUP BY 1
ORDER BY 1;
```

> **What the `tract_geoid` coverage percentage means:**
> Each 311 record is assigned a census tract via a point-in-polygon spatial join using the record's lat/lon coordinates. A record gets `NULL tract_geoid` for four reasons:
>
> | Cause | Example |
> |---|---|
> | **Phone-in complaints** | Caller reports an issue without a specific address — no coordinates recorded |
> | **Citywide complaints** | Noise policy, general agency feedback — no location attached |
> | **Coordinates outside NYC** | Data entry errors or complaints filed from outside the city limits |
> | **Water areas** | Coordinates fall in the Hudson, East River, or harbor rather than on land |
>
> Records with `NULL tract_geoid` flow through raw and staging but are dropped at `fct_request_response_time` via the `INNER JOIN dim_tract ON tract_geoid` — they never reach the equity analysis since they cannot be assigned to a neighborhood. Expect **90–95%** coverage per month. Below 85% indicates a spatial join issue. The percentage is logged during ingestion but not stored as a column in any schema — derive it using the queries above.

---

## 7. Run Great Expectations (Raw Suite)

Fill in your credentials in `great_expectations/uncommitted/config_variables.yml` — this file is gitignored:

```yaml
SNOWFLAKE_USER: "your_user"
SNOWFLAKE_PASSWORD: "your_password"
SNOWFLAKE_ACCOUNT: "your_account_identifier"
SNOWFLAKE_WAREHOUSE: "COMPUTE_WH"
SNOWFLAKE_ROLE: "TRANSFORMER"
```

Run the checkpoint via the helper script from the project root:

```bash
python scripts/run_ge_checkpoint.py raw_311_socrata_checkpoint
```

**Expected output:**
```
Running checkpoint: raw_311_socrata_checkpoint ...

✓ raw_311_socrata_checkpoint PASSED
  7/7 expectations passed
```

If it fails, each broken expectation is printed with its actual result — most commonly `expect_table_row_count_to_be_between` (empty pull) or lat/lon bounds (check your Socrata API token).

---

## 8. Run dbt

### Set up `profiles.yml` (one time only)

dbt reads Snowflake credentials from `~/.dbt/profiles.yml` — a global file that lives outside the project so it's never committed.
Verify dbt can connect (credentials come from the `~/.dbt/profiles.yml` you filled in during step 4):

```bash
cd dbt
dbt debug
```

Look for `Connection test: OK` at the bottom. If it fails, check that your `.env` has the correct `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, and `SNOWFLAKE_PASSWORD`.

### Load ACS demographics (one time only)

dbt's staging and mart models join 311 requests to census tract demographics. The ACS table must exist in Snowflake before dbt can run. Load it now:

```bash
python scripts/load_acs.py
```

**Expected output:**
```
Fetching ACS 2024 5-year estimates (survey years 2020–2024) for NYC census tracts ...
  Fetched 2,168 tracts  (expect ~2,168 for NYC)
Writing to S3 ...
  Written to: s3://nyc-311-equity-mart/raw/acs_demographics/year=2024/part-0001.parquet
Loading into Snowflake RAW.ACS_DEMOGRAPHICS (full replace) ...

Done. Verify in Snowflake:
  SELECT COUNT(*), MAX(vintage_year) FROM NYC_311.RAW.ACS_DEMOGRAPHICS;
  -- Expect 2,300–2,400 rows | vintage_year = 2024 | survey years 2020–2024
  -- (includes water-only and special tracts alongside the ~2,168 land tracts)
```

> ACS releases each December with a ~13-month lag. The 2024 vintage (covering 2020–2024) was released December 2025 and is the latest available. After the initial load, `dag_acs_annual.py` refreshes this table automatically every January 1st.

### Run the models

```bash
cd dbt

# Install packages (if not done in step 2)
dbt deps

# Run staging views
dbt run --select staging
dbt test --select staging

# Run the incremental intermediate model
dbt run --select intermediate

# Run marts (dim_tract → fct_request_response_time → fct_equity_splits)
dbt run --select marts
dbt test --select marts

# Run all tests including custom assert_percentile_ordering
dbt test
```

**Check key output in Snowflake:**

```sql
-- Verify marts are populated
SELECT COUNT(*) FROM NYC_311.MARTS.FCT_EQUITY_SPLITS;
-- Expect > 0 rows (more rows after backfill)

SELECT COUNT(*) FROM NYC_311.MARTS.DIM_TRACT;
-- Expect ~2168

-- Sanity-check equity scores
SELECT complaint_type, AVG(equity_score) AS avg_score
FROM NYC_311.MARTS.FCT_EQUITY_SPLITS
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10;
-- Scores should be clustered around 1.0, with some outliers
-- All exactly 1.0 = bug in city_p90 join
```

---

## 9. Run the Historical Backfill

This loads all NYC 311 data from 2020 to the present. Run it **once**, manually, outside of Airflow:

```bash
python -m ingestion.backfill
```

> The Socrata dataset (`erm2-nwe9`) confirmed to have no records before 2020. Older data was either not migrated or lives under a different dataset ID.

- Iterates month by month (Jan 2020 → present)
- ~75 months × ~200K avg rows
- **Expect 2–3 hours**
- Idempotent — safe to re-run if interrupted; each month overwrites the same S3 key

Progress is logged to stdout:
```
2025-01-01 10:12:03 INFO 2010-01: done (187234 rows)
2025-01-01 10:12:41 INFO 2010-02: done (171892 rows)
...
```

After it finishes, re-run dbt to rebuild marts on the full dataset:

```bash
cd dbt
dbt run --full-refresh --select intermediate
dbt run --select marts
```

---

## 10. Start Airflow

Airflow runs locally via Docker Compose and takes over daily incremental loads.

### How the daily increment works

The DAG runs at 6 AM UTC every day and only processes records updated since the last run — not the full 35M rows.

**Watermark — where the DAG picks up from:**
```python
watermark = MAX(resolution_action_updated_date FROM RAW.SOCRATA_311) - 48h
```
The watermark is read from the data already in Snowflake, not from the clock. This means:
- If the container was off for 3 days, the next run fetches all 3 days automatically
- Missing days are always recovered on the next run regardless of how long the gap was

**Why the 48-hour buffer exists — two reasons:**

*1. Late-arriving Socrata writes:* When a 311 request closes, Socrata can take hours to reflect the updated `resolution_action_updated_date` in the API. Without the buffer, records updated just before the watermark cutoff could be missed entirely.

*2. Open → closed transitions:* A request created in January may stay open for weeks before closing in February. When it closes, its `resolution_action_updated_date` changes. The buffer ensures that closure is always captured on the next run.

The buffer works together with dbt's `incremental_strategy='merge'` in `int_311_with_response_time`:
```
Jan 15: request created → loaded with response_time_hours = NULL (still open)
Feb 3:  request closes  → watermark catches it → dbt MERGE updates the existing row
                          response_time_hours = DATEDIFF(Jan 15, Feb 3) = 19 days
```
Without both mechanisms, open requests would never get their response times calculated — they would stay NULL forever.

**`catchup=False` — what happens if the container is off:**
Airflow does not replay missed scheduled runs. When the container restarts, it runs the next scheduled instance only. The missed DAG executions are skipped — but because the watermark is data-driven, the next run automatically fetches everything since the last successful load. No data is lost.

```bash
# First time only — initialize the Airflow DB and create admin user
docker-compose up airflow-init

# Start all services (webserver + scheduler + postgres)
docker-compose up -d

# Check they're running
docker-compose ps
```

Open the Airflow UI at **http://localhost:8080** — login: `admin` / `admin`

**Enable the DAGs:**
1. Find `nyc_311_daily_incremental` → toggle it **On**
2. Find `dag_acs_annual` → toggle it **On**
3. Leave `dag_311_backfill` Off (manual trigger only)

**Trigger a manual test run:**
1. Click `nyc_311_daily_incremental` → **Trigger DAG** (▶ button)
2. Watch the task graph — all tasks should turn green within ~10 minutes

**To trigger a backfill for a specific month via Airflow:**
```bash
docker-compose exec airflow-webserver \
  airflow dags trigger dag_311_backfill \
  --conf '{"year": 2023, "month": 6}'
```

**To stop Airflow:**
```bash
docker-compose down
```

---

## 11. Launch the Dashboard

```bash
streamlit run dashboard/app.py
```

Open **http://localhost:8501** in your browser.

**Pages:**

| Sidebar Item | What It Shows |
|---|---|
| Borough Map | Choropleth by census tract — color = equity score. Filter by complaint type and borough. |
| Equity by Income | Bar chart + scatter: income quintile vs P90 response time. Metric callouts for top vs bottom quintile. |
| Complaint Breakdown | Heatmap of top 20 complaint types × borough. Toggle between P50, P90, or volume. |
| Key Findings | Complaint type equity gaps by agency, borough × income heatmap, trend over time, AI-generated synthesis. |

> Queries are cached for 1 hour. Force a refresh with `Ctrl+Shift+R` in the browser or restart the Streamlit process.

**Deploy to Streamlit Cloud (optional):**
1. Push the repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io/) → New app → point to `dashboard/app.py`
3. In **Advanced settings → Secrets**, paste the contents of your `secrets.toml`

---

## 12. AI Synthesis

The **Key Findings** page includes an AI-generated root-cause assessment and actionable recommendations, produced by [Groq](https://console.groq.com) (free tier, no credit card required) using the `llama-3.3-70b-versatile` model.

### How it works

The synthesis is generated **once per unique dataset** and stored permanently in Snowflake. Page loads, server restarts, and multiple concurrent users all read from Snowflake — Groq is never called more than once per pipeline run.

```
Page load
  └─► query MARTS.AI_SYNTHESIS_CACHE (data_hash)
        ├─ complete row found → display synthesis, no API call
        ├─ pending row found  → "being generated" message, no API call
        └─ no row             → show "Generate AI Analysis" button

Button click
  └─► INSERT pending row (distributed lock — only one session wins)
        └─► call Groq API (one request)
              └─► UPDATE row to complete with synthesis text
                    └─► st.rerun() → page reads complete row → button gone
```

`data_hash` is an MD5 of the three findings (complaint-type gaps, borough × quintile heatmap, equity trend). When the pipeline loads new data the hash changes, a new row is needed, and the button reappears once.

### Setup

1. Get a free API key at [console.groq.com](https://console.groq.com) → **API Keys** → **Create API Key**

2. Add it to `.streamlit/secrets.toml` **above** the `[snowflake]` section (TOML parses keys after a section header as belonging to that section):

```toml
GROQ_API_KEY = "gsk_..."

[snowflake]
account   = "..."
...
```

3. Create the cache table in Snowflake (the app also creates it automatically on startup):

```sql
CREATE TABLE IF NOT EXISTS MARTS.AI_SYNTHESIS_CACHE (
    data_hash      VARCHAR PRIMARY KEY,
    status         VARCHAR DEFAULT 'pending',
    synthesis_text VARCHAR,
    generated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

4. Launch the dashboard, navigate to **Key Findings**, and click **Generate AI Analysis**. The button disappears after the first successful generation and the synthesis persists indefinitely.

### Quota

Groq free tier: **30 requests per minute**, resets every minute. At most one request per pipeline run means the free tier is never exhausted under normal operation.

---

## 13. Project Structure


```
nyc-311-service-equity-mart/
├── .env.example                    ← copy to .env and fill in
├── .gitignore
├── requirements.txt
├── docker-compose.yml              ← local Airflow
├── PLAN.md                         ← full technical plan
│
├── ingestion/
│   ├── config.py                   ← reads .env
│   ├── socrata_client.py           ← API fetch + watermark
│   ├── acs_client.py               ← Census ACS pull
│   ├── tract_geometry.py           ← geopandas sjoin
│   ├── s3_writer.py                ← write Parquet to S3
│   ├── snowflake_loader.py         ← COPY INTO Snowflake
│   └── backfill.py                 ← one-time historical load
│
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml.example        ← copy to ~/.dbt/profiles.yml
│   ├── models/
│   │   ├── staging/                ← views; rename + cast raw data
│   │   ├── intermediate/           ← incremental merge; compute response_time_hours
│   │   └── marts/                  ← dim_tract, fct_request_response_time, fct_equity_splits
│   └── tests/
│       └── assert_percentile_ordering.sql
│
├── great_expectations/
│   ├── checkpoints/                ← 4 checkpoints, one per pipeline stage
│   └── expectations/               ← expectation suites (JSON)
│
├── airflow/
│   └── dags/
│       ├── dag_311_daily_incremental.py   ← runs at 6 AM UTC daily
│       ├── dag_311_backfill.py            ← manual trigger only
│       └── dag_acs_annual.py              ← runs Jan 1 each year
│
└── dashboard/
    ├── app.py                      ← Streamlit entrypoint
    ├── pages/
    │   ├── 01_borough_map.py
    │   ├── 02_equity_by_income.py
    │   ├── 03_complaint_breakdown.py
    │   └── 04_key_findings.py
    └── utils/
        ├── snowflake_conn.py       ← cached Snowflake connection
        └── chart_helpers.py        ← reusable Plotly helpers
```

---

## 13. Data Model

### Sources → Raw

| Table | Schema | Description |
|---|---|---|
| `SOCRATA_311` | `RAW` | Append-only 311 requests from Socrata. All VARCHAR; dedup in staging. |
| `ACS_DEMOGRAPHICS` | `RAW` | Census ACS 5-year estimates. Full replace annually. |

### dbt Models

```
RAW.SOCRATA_311
    └─► stg_311_requests (view)
            └─► int_311_with_response_time (incremental merge)
                    └─► fct_request_response_time (table)  ←── dim_tract
                                └─► fct_equity_splits (table)  ←── dim_tract

RAW.ACS_DEMOGRAPHICS
    └─► stg_acs_demographics (view)
            └─► dim_tract (table)
```

### Key Mart Columns

**`fct_equity_splits`** — grain: `complaint_type × tract × month`

| Column | Type | Description |
|---|---|---|
| `tract_geoid` | VARCHAR | Census tract ID |
| `complaint_type` | VARCHAR | e.g. `RODENT`, `HEAT/HOT WATER` |
| `request_month` | DATE | First day of the month |
| `income_quintile` | INT | 1 = lowest income, 5 = highest |
| `p50_hours` | FLOAT | Median response time |
| `p90_hours` | FLOAT | 90th percentile response time |
| `equity_score` | FLOAT | `tract_p90 / city_p90` — higher = worse service |
| `request_count` | INT | Total closed requests in this group |

**`dim_tract`** — grain: one row per NYC census tract

| Column | Type | Description |
|---|---|---|
| `tract_geoid` | VARCHAR | Census 2020 tract ID (joins to GeoJSON) |
| `median_household_income` | INT | ACS B19013 |
| `income_quintile` | INT | NTILE(5) across all NYC tracts |
| `pct_below_poverty` | FLOAT | % of population below federal poverty line |

---

## 15. Troubleshooting

**`COPY INTO` returns 0 rows**
- Check the external stage: `SHOW STAGES IN SCHEMA NYC_311.RAW;`
- Verify the S3 path exactly matches: `LIST @NYC_311.RAW.S3_STAGE/raw/socrata_311/;`
- Confirm AWS credentials are correct in `.env`

**`tract_geoid` is NULL for most rows**
- The GeoJSON cache may be corrupted. Delete it and re-download: `rm ingestion/data/nyc_tracts.geojson`
- Verify lat/lon values are in NYC bounds (lat 40.4–41.0, lon -74.3–-73.7)

**dbt test fails on `unique_key` in staging**
- The `QUALIFY` window in `stg_311_requests` deduplicates by `updated_at DESC`. If `updated_at` is NULL for many rows, the dedup won't work. Check: `SELECT COUNT(*) FROM RAW.SOCRATA_311 WHERE resolution_action_updated_date IS NULL;`

**Equity score is exactly 1.0 for all rows**
- The `city_p90` subquery in `fct_equity_splits` is returning the same value as the tract p90. Check whether `fct_request_response_time` has data across multiple tracts: `SELECT COUNT(DISTINCT tract_geoid) FROM MARTS.FCT_REQUEST_RESPONSE_TIME;`

**Airflow task fails with `KeyError` on env var**
- Never import `Config()` at the top of a DAG file. It must be instantiated inside the callable. Check that all env vars are set in `docker-compose.yml` under `environment`.

**Streamlit shows empty charts**
- The mart tables need data. Check: `SELECT COUNT(*) FROM NYC_311.MARTS.FCT_EQUITY_SPLITS;`
- If 0, run the single-day test (Step 6) before launching the dashboard.

**`dbt run` fails with schema not found**
- The `generate_schema_name` macro uses the schema name from `+schema:` in `dbt_project.yml` verbatim (uppercase). Make sure the schemas `STAGING`, `INTERMEDIATE`, and `MARTS` exist in Snowflake (created in Step 5).
