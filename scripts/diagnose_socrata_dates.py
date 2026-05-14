"""
Diagnose what years of data are available in the Socrata 311 dataset.
Run from the project root:

    python scripts/diagnose_socrata_dates.py

Checks one sample month per year to find where data actually starts
and what the created_date format looks like for each era.
"""
import sys

sys.path.insert(0, ".")

from sodapy import Socrata
from ingestion.config import Config


def main() -> None:
    cfg = Config()
    client = Socrata("data.cityofnewyork.us", cfg.socrata_app_token, timeout=60)

    print(f"Dataset: {cfg.socrata_dataset_id}")
    print(f"Checking data availability by year ...\n")

    years = [2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

    first_year_with_data = None

    for year in years:
        try:
            result = client.get(
                cfg.socrata_dataset_id,
                where=(
                    f"created_date >= '{year}-01-01T00:00:00' "
                    f"AND created_date <= '{year}-01-31T23:59:59'"
                ),
                order="created_date ASC",
                limit=1,
            )

            if result:
                record = result[0]
                created = record.get("created_date", "N/A")
                unique_key = record.get("unique_key", "N/A")
                print(f"  {year}: ✓ found  |  created_date = '{created}'  |  unique_key = {unique_key}")
                if first_year_with_data is None:
                    first_year_with_data = year
            else:
                print(f"  {year}: ✗ no records")

        except Exception as e:
            print(f"  {year}: ERROR — {e}")

    client.close()

    print()
    if first_year_with_data:
        print(f"Earliest year with data: {first_year_with_data}")
        print(f"Recommended start_year in backfill.py: {first_year_with_data}")
    else:
        print("No data found for any year — check your SOCRATA_APP_TOKEN")


if __name__ == "__main__":
    main()
