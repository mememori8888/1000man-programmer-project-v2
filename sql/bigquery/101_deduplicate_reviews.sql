-- Mart layer: deduplicate parsed review rows into fact_reviews.
-- `raw_reviews_parsed` is the staging view/table produced from raw payload parsing.

create or replace table `${PROJECT_ID}.${DATASET}.fact_reviews`
partition by review_date
cluster by facility_id, review_id
as
select
  review_id,
  facility_id,
  rating,
  review_text,
  review_date,
  extracted_at,
  loaded_at
from (
  select
    *,
    row_number() over (
      partition by facility_id, review_id
      order by extracted_at desc, loaded_at desc
    ) as row_num
  from `${PROJECT_ID}.${DATASET}.raw_reviews_parsed`
)
where row_num = 1;
