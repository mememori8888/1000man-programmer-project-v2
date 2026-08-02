-- Parse raw BrightData review payloads into row-shaped staging data.
-- Supports either:
--   1. {"snapshot_id": "...", "data": [ ...review objects... ]}
--   2. [ ...review objects... ]

create or replace table `${PROJECT_ID}.${DATASET}.raw_reviews_parsed` as
with source_rows as (
  select
    source_run_id,
    raw_object_uri,
    raw_payload,
    extracted_at,
    loaded_at,
    payload_sha256
  from `${PROJECT_ID}.${DATASET}.raw_reviews`
  where dataset_kind = 'reviews'
),
review_items as (
  select
    source_run_id,
    raw_object_uri,
    extracted_at,
    loaded_at,
    payload_sha256,
    review_json
  from source_rows,
  unnest(
    coalesce(
      json_query_array(raw_payload, '$.data'),
      json_query_array(raw_payload, '$')
    )
  ) as review_json
),
normalized as (
  select
    source_run_id,
    raw_object_uri,
    payload_sha256,
    coalesce(
      nullif(json_value(review_json, '$.review_id'), ''),
      nullif(json_value(review_json, '$.review_gid'), ''),
      nullif(json_value(review_json, '$.id'), ''),
      to_hex(sha256(to_json_string(review_json)))
    ) as review_id,
    coalesce(
      nullif(json_value(review_json, '$.facility_id'), ''),
      nullif(json_value(review_json, '$.place_id'), ''),
      nullif(json_value(review_json, '$.input.facility_id'), ''),
      nullif(json_value(review_json, '$.input.url'), ''),
      nullif(json_value(review_json, '$.url'), '')
    ) as facility_id,
    coalesce(
      safe_cast(json_value(review_json, '$.rating') as int64),
      safe_cast(json_value(review_json, '$.review_rating') as int64)
    ) as rating,
    coalesce(
      json_value(review_json, '$.text'),
      json_value(review_json, '$.review_text'),
      json_value(review_json, '$.review'),
      json_value(review_json, '$.comment')
    ) as review_text,
    coalesce(
      safe_cast(json_value(review_json, '$.review_date') as date),
      safe_cast(substr(json_value(review_json, '$.timestamp'), 1, 10) as date),
      safe_cast(substr(json_value(review_json, '$.date'), 1, 10) as date)
    ) as review_date,
    extracted_at,
    loaded_at,
    to_json_string(review_json) as raw_review_json
  from review_items
)
select *
from normalized
where review_id is not null
  and facility_id is not null;
