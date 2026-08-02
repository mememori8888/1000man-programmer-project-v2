-- Parse raw BrightData facility payloads into a dimension staging table.
-- Supports either:
--   1. {"snapshot_id": "...", "data": [ ...facility objects... ]}
--   2. [ ...facility objects... ]

create or replace table `${PROJECT_ID}.${DATASET}.dim_facilities` as
with source_rows as (
  select
    source_run_id,
    raw_object_uri,
    raw_payload,
    extracted_at,
    loaded_at
  from `${PROJECT_ID}.${DATASET}.raw_facilities`
  where dataset_kind = 'facilities'
),
facility_items as (
  select
    source_run_id,
    raw_object_uri,
    extracted_at,
    loaded_at,
    facility_json
  from source_rows,
  unnest(
    coalesce(
      json_query_array(raw_payload, '$.data'),
      json_query_array(raw_payload, '$')
    )
  ) as facility_json
),
normalized as (
  select
    coalesce(
      nullif(json_value(facility_json, '$.facility_id'), ''),
      nullif(json_value(facility_json, '$.place_id'), ''),
      nullif(json_value(facility_json, '$.fid'), ''),
      nullif(json_value(facility_json, '$.gid'), ''),
      nullif(json_value(facility_json, '$.url'), ''),
      to_hex(sha256(to_json_string(facility_json)))
    ) as facility_id,
    coalesce(
      json_value(facility_json, '$.facility_type'),
      json_value(facility_json, '$.category'),
      json_value(facility_json, '$.type')
    ) as facility_type,
    coalesce(
      json_value(facility_json, '$.facility_name'),
      json_value(facility_json, '$.name'),
      json_value(facility_json, '$.title')
    ) as facility_name,
    coalesce(
      json_value(facility_json, '$.address'),
      json_value(facility_json, '$.full_address')
    ) as address,
    coalesce(
      json_value(facility_json, '$.google_map_url'),
      json_value(facility_json, '$.url'),
      json_value(facility_json, '$.maps_url')
    ) as google_map_url,
    coalesce(
      json_value(facility_json, '$.fid'),
      json_value(facility_json, '$.place_id'),
      json_value(facility_json, '$.gid')
    ) as fid,
    extracted_at as first_seen_at,
    loaded_at as updated_at,
    source_run_id,
    raw_object_uri
  from facility_items
),
deduped as (
  select
    *,
    row_number() over (
      partition by facility_id
      order by updated_at desc, first_seen_at desc
    ) as row_num
  from normalized
  where facility_id is not null
)
select
  facility_id,
  facility_type,
  facility_name,
  address,
  google_map_url,
  fid,
  first_seen_at,
  updated_at
from deduped
where row_num = 1;
