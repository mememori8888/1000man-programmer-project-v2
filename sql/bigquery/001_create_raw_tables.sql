-- BigQuery raw layer. Replace `${PROJECT_ID}` and `${DATASET}` in deployment.

create table if not exists `${PROJECT_ID}.${DATASET}.raw_reviews` (
  source_run_id string not null,
  raw_object_uri string not null,
  raw_payload string,
  source_system string not null,
  extracted_at timestamp not null,
  loaded_at timestamp not null default current_timestamp(),
  payload_sha256 string,
  dataset_kind string not null
)
partition by date(extracted_at)
cluster by source_run_id, dataset_kind;

create table if not exists `${PROJECT_ID}.${DATASET}.raw_facilities` (
  source_run_id string not null,
  raw_object_uri string not null,
  raw_payload string,
  source_system string not null,
  extracted_at timestamp not null,
  loaded_at timestamp not null default current_timestamp(),
  payload_sha256 string,
  dataset_kind string not null
)
partition by date(extracted_at)
cluster by source_run_id, dataset_kind;

create table if not exists `${PROJECT_ID}.${DATASET}.raw_serp_responses` (
  source_run_id string not null,
  raw_object_uri string not null,
  raw_payload string,
  source_system string not null,
  extracted_at timestamp not null,
  loaded_at timestamp not null default current_timestamp(),
  payload_sha256 string,
  dataset_kind string not null
)
partition by date(extracted_at)
cluster by source_run_id, dataset_kind;
