-- Atomic fact: one row per closed 311 request that can be geo-joined to a census tract.
-- Rows without a matching tract (~3% of requests) are excluded via the INNER JOIN.
SELECT
    r.unique_key,
    r.created_at,
    r.closed_at,
    DATE_TRUNC('month', r.created_at)           AS request_month,
    r.complaint_type,
    r.descriptor,
    r.agency_code,
    r.borough,
    r.incident_zip,
    r.channel_type,
    r.tract_geoid,
    r.latitude,
    r.longitude,
    DATEDIFF('hour', r.created_at, r.closed_at) AS response_time_hours
FROM {{ ref('int_311_with_response_time') }} r
INNER JOIN {{ ref('dim_tract') }} t
    ON r.tract_geoid = t.tract_geoid
WHERE r.closed_at IS NOT NULL
  AND r.closed_at > r.created_at
