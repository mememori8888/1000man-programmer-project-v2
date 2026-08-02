# ELT implementation notes

This project moves heavy matching and deduplication out of Python and into BigQuery.

## Current implemented boundary

- `elt-raw-write` validates a BrightData `.json` or `.csv` export.
- It writes the untouched payload under a deterministic raw object path.
- It writes a sidecar manifest with `source_run_id`, SHA-256, byte size, object name, and extraction time.
- The same object can be written locally for tests or uploaded to GCS when `google-cloud-storage` is installed.
- `elt-brightdata build-items` converts private-data CSV rows into BrightData Dataset API input items.
- `elt-brightdata validate-input` checks the private-data CSV header, selected row range, and expected item count before a paid Dataset API run.
- `elt-brightdata run-dataset` runs the BrightData Dataset API `trigger -> progress -> snapshot` flow and writes raw JSON output to a file.
- `elt-brightdata run-serp` preserves the SERP API request path used by the existing demo for focused diagnostics and later relevance-rank work.
- `.github/workflows/serp-reviews-smoke.yml` exposes that SERP diagnostic path as a manual workflow.
- `.github/workflows/serp-relevance-extract.yml` stores SERP responses as `serp_relevance` raw objects and loads them into `raw_serp_responses`.
- `.github/workflows/serp-relevance-batch.yml` turns either a private-data facility CSV or BigQuery recent `fact_reviews` into a bounded SERP matrix, stores each response with the same raw object contract, then refreshes the SERP rank fact tables.
- `.github/workflows/brightdata-extract.yml` keeps the BrightData result file inside the same job, stores it as a raw object, and only passes small metadata through GitHub outputs.
- `elt-bigquery replay-gcs-raw` and `.github/workflows/raw-object-replay.yml` replay an existing GCS raw object plus its manifest into BigQuery without rerunning BrightData.
- `elt-bigquery export-csv` and `.github/workflows/bigquery-export.yml` provide the compatibility path for users who still need CSV output from `fact_reviews` or `dim_facilities`.
- `.github/workflows/preflight.yml` validates repository settings before paid or long-running workflows are launched.

## Next boundary

GitHub Actions can call the extractor after each BrightData job and upload raw files to GCS. When `ELT_RAW_GCS_BUCKET`, `ELT_BIGQUERY_PROJECT_ID`, and `ELT_BIGQUERY_DATASET` repository variables are configured, the BrightData workflows also insert one metadata-rich raw row into BigQuery. IssueOps routes approved jobs through that BrightData extract boundary, so raw rows contain the external source payload rather than the Issue request body.
When `run_transform` is enabled, the same workflow immediately runs the managed BigQuery SQL chain after raw load, so IssueOps jobs can move from Extract to Load to Transform without a separate manual action.
Before the raw insert, the extractor workflow runs `001_create_raw_tables.sql` with `create table if not exists`; this keeps the first production run from failing just because the raw tables have not been bootstrapped yet.
The extractor workflow invokes `elt-raw-write` once with both local and optional GCS destinations. That preserves one manifest, one object name, and one SHA-256 across local artifacts, GCS, and the BigQuery raw row.

The current BigQuery contract is intentionally simple: one raw object becomes one row with `raw_payload`, `source_run_id`, `raw_object_uri`, `payload_sha256`, and timestamps. Parsing into `raw_reviews_parsed`, `dim_facilities`, and `fact_reviews` is handled by SQL files in `sql/bigquery`.
SERP relevance responses use the same contract through `raw_serp_responses`; `020_parse_raw_serp_responses.sql` and `120_build_review_relevance_ranks.sql` convert those raw responses into `fact_review_relevance_ranks` without changing the extractor.

CSV compatibility output is also handled by BigQuery, not Python loops. BigQuery extract jobs write CSV shards directly to GCS, which keeps runner memory and disk usage independent of table size.

Recovery follows the same raw-first contract: if a previous run produced a raw object in GCS, replay the raw object into BigQuery and rerun the transform SQL. That replaces the old CSV batch recovery path with an idempotent DWH-centered flow.

Compatibility verification is explicit: `.github/workflows/compatibility-audit.yml` loads one legacy CSV from the private data repo into a temporary BigQuery audit table, then compares row counts, distinct key counts, and key-diff samples against a v2 mart table. This keeps the final demo-vs-v2 proof inside BigQuery instead of pulling large tables into Python memory.
