-- Aggregated equity fact: grain = complaint_type × tract × month.
-- equity_score = this tract's p90 / city-wide p90 for the same complaint_type + month.
-- Values > 1.0 mean the tract waits longer than the city average.
WITH city_p90 AS (
    SELECT
        complaint_type,
        request_month,
        PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY response_time_hours) AS p90_hours
    FROM {{ ref('fct_request_response_time') }}
    GROUP BY complaint_type, request_month
)

SELECT
    f.tract_geoid,
    f.complaint_type,
    f.request_month,
    f.borough,
    d.income_quintile,
    d.median_household_income,
    d.pct_below_poverty,
    d.total_population,
    d.pop_black,
    d.pop_hispanic,
    COUNT(*)                                                                    AS request_count,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY f.response_time_hours)        AS p50_hours,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY f.response_time_hours)        AS p75_hours,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY f.response_time_hours)        AS p90_hours,
    ROUND(
        PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY f.response_time_hours)
        / NULLIF(c.p90_hours, 0),
        4
    )                                                                           AS equity_score,
    CURRENT_TIMESTAMP()                                                         AS mart_refreshed_at
FROM {{ ref('fct_request_response_time') }} f
JOIN {{ ref('dim_tract') }} d
    ON f.tract_geoid = d.tract_geoid
JOIN city_p90 c
    ON f.complaint_type = c.complaint_type
    AND f.request_month  = c.request_month
GROUP BY
    f.tract_geoid,
    f.complaint_type,
    f.request_month,
    f.borough,
    d.income_quintile,
    d.median_household_income,
    d.pct_below_poverty,
    d.total_population,
    d.pop_black,
    d.pop_hispanic,
    c.p90_hours
