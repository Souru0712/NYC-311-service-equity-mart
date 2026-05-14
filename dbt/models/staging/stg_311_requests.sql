WITH raw AS (
    SELECT *
    FROM {{ source('raw', 'socrata_311') }}
    WHERE unique_key IS NOT NULL
),

deduped AS (
    SELECT
        unique_key,
        TO_TIMESTAMP_NTZ(created_date)                      AS created_at,
        TO_TIMESTAMP_NTZ(closed_date)                       AS closed_at,
        TO_TIMESTAMP_NTZ(resolution_action_updated_date)    AS updated_at,
        UPPER(TRIM(agency))                                 AS agency_code,
        UPPER(TRIM(agency_name))                            AS agency_name,
        UPPER(TRIM(complaint_type))                         AS complaint_type,
        UPPER(TRIM(descriptor))                             AS descriptor,
        UPPER(TRIM(location_type))                          AS location_type,
        TRIM(incident_zip)                                  AS incident_zip,
        TRIM(incident_address)                              AS incident_address,
        UPPER(TRIM(borough))                                AS borough,
        UPPER(TRIM(status))                                 AS status,
        TRIM(open_data_channel_type)                        AS channel_type,
        resolution_description,
        CAST(latitude AS FLOAT)                             AS latitude,
        CAST(longitude AS FLOAT)                            AS longitude,
        tract_geoid,
        ingestion_timestamp
    FROM raw
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY unique_key
        ORDER BY TO_TIMESTAMP_NTZ(resolution_action_updated_date) DESC NULLS LAST
    ) = 1
)

SELECT * FROM deduped
