SELECT
    REPLACE(geo_id, '1400000US', '')    AS tract_geoid,
    '36' || county || tract             AS fips_full,
    state                               AS state_fips,
    county                              AS county_fips,
    tract                               AS tract_code,
    county_fips                         AS nyc_county_fips,
    CAST(b19013_001e AS INTEGER)        AS median_household_income,
    CAST(b01003_001e AS INTEGER)        AS total_population,
    CAST(b17001_002e AS INTEGER)        AS population_below_poverty,
    CAST(b03002_003e AS INTEGER)        AS pop_white_non_hispanic,
    CAST(b03002_012e AS INTEGER)        AS pop_hispanic,
    CAST(b03002_004e AS INTEGER)        AS pop_black,
    vintage_year
FROM {{ source('raw', 'acs_demographics') }}
WHERE geo_id IS NOT NULL
