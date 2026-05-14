SELECT
    tract_geoid,
    fips_full,
    state_fips,
    county_fips,
    tract_code,
    median_household_income,
    total_population,
    population_below_poverty,
    ROUND(
        100.0 * population_below_poverty / NULLIF(total_population, 0),
        2
    )                                                   AS pct_below_poverty,
    pop_white_non_hispanic,
    pop_hispanic,
    pop_black,
    NTILE(5) OVER (ORDER BY median_household_income)   AS income_quintile,
    vintage_year
FROM {{ ref('stg_acs_demographics') }}
