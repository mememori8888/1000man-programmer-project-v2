-- Build the clean relevance rank fact table from parsed SERP responses.

create or replace table `${PROJECT_ID}.${DATASET}.fact_review_relevance_ranks`
cluster by facility_id, review_id
as
select
  facility_id,
  review_id,
  rank_position,
  rank_source,
  review_text,
  author_name,
  rating,
  extracted_at,
  loaded_at
from (
  select
    *,
    row_number() over (
      partition by facility_id, review_id, rank_source
      order by extracted_at desc, loaded_at desc, rank_position asc
    ) as row_num
  from `${PROJECT_ID}.${DATASET}.raw_serp_relevance_parsed`
)
where row_num = 1;
