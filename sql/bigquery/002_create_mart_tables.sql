-- BigQuery mart layer. Replace `${PROJECT_ID}` and `${DATASET}` in deployment.

create table if not exists `${PROJECT_ID}.${DATASET}.dim_facilities` (
  facility_id string not null,
  facility_type string,
  facility_name string,
  address string,
  google_map_url string,
  fid string,
  first_seen_at timestamp,
  updated_at timestamp
)
cluster by facility_type, facility_id;

create table if not exists `${PROJECT_ID}.${DATASET}.fact_reviews` (
  review_id string not null,
  facility_id string not null,
  rating int64,
  review_text string,
  review_date date,
  extracted_at timestamp,
  loaded_at timestamp
)
partition by review_date
cluster by facility_id, review_id;
