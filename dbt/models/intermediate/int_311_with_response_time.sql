{{
    config(
        unique_key='unique_key',
        incremental_strategy='merge',
        on_schema_change='append_new_columns'
    )
}}

SELECT
    unique_key,
    created_at,
    closed_at,
    updated_at,
    agency_code,
    agency_name,
    complaint_type,
    descriptor,
    location_type,
    incident_zip,
    incident_address,
    borough,
    status,
    channel_type,
    resolution_description,
    latitude,
    longitude,
    tract_geoid,
    CASE
        WHEN closed_at IS NOT NULL AND closed_at > created_at
            THEN DATEDIFF('hour', created_at, closed_at)
        ELSE NULL
    END                                                         AS response_time_hours,
    CASE
        WHEN closed_at IS NOT NULL AND closed_at > created_at THEN 'closed'
        WHEN UPPER(status) = 'OPEN'                           THEN 'open'
        ELSE 'other'
    END                                                         AS resolution_status
FROM {{ ref('stg_311_requests') }}

{% if is_incremental() %}
WHERE updated_at >= (
    SELECT DATEADD('hour', -48, MAX(updated_at))
    FROM {{ this }}
)
{% endif %}
