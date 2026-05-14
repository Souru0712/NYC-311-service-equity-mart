-- Fails if any row has p50 > p75 or p75 > p90 (statistical invariant)
SELECT
    tract_geoid,
    complaint_type,
    request_month,
    p50_hours,
    p75_hours,
    p90_hours
FROM {{ ref('fct_equity_splits') }}
WHERE p50_hours > p75_hours
   OR p75_hours > p90_hours
