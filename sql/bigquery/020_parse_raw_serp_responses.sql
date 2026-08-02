-- Staging layer: parse raw BrightData SERP response envelopes into row-shaped
-- relevance rank data.
-- Expected envelope:
--   {"request": {"url": "...", "zone": "..."}, "response": {...SERP payload...}}
-- The response shape can vary by BrightData zone, so this SQL checks several common arrays.

create or replace table `${PROJECT_ID}.${DATASET}.raw_serp_relevance_parsed`
partition by date(extracted_at)
cluster by facility_id, review_id
as
with source_rows as (
  select
    source_run_id,
    raw_object_uri,
    raw_payload,
    extracted_at,
    loaded_at,
    payload_sha256,
    json_value(raw_payload, '$.request.url') as request_url,
    json_value(raw_payload, '$.request.facility_id') as request_facility_id,
    json_value(raw_payload, '$.request.zone') as zone_name
  from `${PROJECT_ID}.${DATASET}.raw_serp_responses`
  where dataset_kind = 'serp_relevance'
),
rank_items as (
  select
    source_run_id,
    raw_object_uri,
    extracted_at,
    loaded_at,
    payload_sha256,
    request_url,
    request_facility_id,
    zone_name,
    rank_source,
    rank_offset + 1 as rank_position,
    item_json
  from source_rows,
  unnest(
    coalesce(
      json_query_array(raw_payload, '$.response.reviews'),
      json_query_array(raw_payload, '$.response.place.reviews'),
      json_query_array(raw_payload, '$.response.organic'),
      json_query_array(raw_payload, '$.response.results'),
      json_query_array(raw_payload, '$.response.data'),
      json_query_array(raw_payload, '$.response'),
      array<string>[]
    )
  ) as item_json with offset as rank_offset
  cross join unnest([
    case
      when json_query_array(raw_payload, '$.response.reviews') is not null then 'response.reviews'
      when json_query_array(raw_payload, '$.response.place.reviews') is not null then 'response.place.reviews'
      when json_query_array(raw_payload, '$.response.organic') is not null then 'response.organic'
      when json_query_array(raw_payload, '$.response.results') is not null then 'response.results'
      when json_query_array(raw_payload, '$.response.data') is not null then 'response.data'
      else 'response'
    end
  ]) as rank_source
),
normalized as (
  select
    coalesce(
      nullif(json_value(item_json, '$.facility_id'), ''),
      nullif(json_value(item_json, '$.place_id'), ''),
      nullif(json_value(item_json, '$.fid'), ''),
      nullif(json_value(item_json, '$.gid'), ''),
      nullif(request_facility_id, ''),
      nullif(json_value(item_json, '$.url'), ''),
      nullif(request_url, '')
    ) as facility_id,
    coalesce(
      nullif(json_value(item_json, '$.review_id'), ''),
      nullif(json_value(item_json, '$.review_gid'), ''),
      nullif(json_value(item_json, '$.id'), ''),
      to_hex(sha256(to_json_string(item_json)))
    ) as review_id,
    rank_position,
    rank_source,
    coalesce(
      json_value(item_json, '$.text'),
      json_value(item_json, '$.review_text'),
      json_value(item_json, '$.review'),
      json_value(item_json, '$.snippet'),
      json_value(item_json, '$.description')
    ) as review_text,
    coalesce(
      json_value(item_json, '$.author_name'),
      json_value(item_json, '$.author'),
      json_value(item_json, '$.user.name'),
      json_value(item_json, '$.name')
    ) as author_name,
    coalesce(
      safe_cast(json_value(item_json, '$.rating') as int64),
      safe_cast(json_value(item_json, '$.review_rating') as int64)
    ) as rating,
    request_url,
    zone_name,
    extracted_at,
    loaded_at,
    source_run_id,
    raw_object_uri,
    payload_sha256,
    to_json_string(item_json) as raw_rank_json
  from rank_items
)
select *
from normalized
where facility_id is not null
  and rank_position is not null;
