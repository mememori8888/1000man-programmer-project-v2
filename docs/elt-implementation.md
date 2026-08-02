# ELT implementation notes

This project moves heavy matching and deduplication out of Python and into BigQuery.

## Current implemented boundary

- `elt-raw-write` validates a BrightData `.json` or `.csv` export.
- It writes the untouched payload under a deterministic raw object path.
- It writes a sidecar manifest with `source_run_id`, SHA-256, byte size, object name, and extraction time.
- The same object can be written locally for tests or uploaded to GCS when `google-cloud-storage` is installed.
- `elt-brightdata build-items` converts private-data CSV rows into BrightData Dataset API input items.
- `elt-brightdata run-dataset` runs the BrightData Dataset API `trigger -> progress -> snapshot` flow and writes raw JSON output.
- `elt-brightdata run-serp` preserves the SERP API request path used by the existing demo for focused diagnostics and later relevance-rank work.

## Next boundary

GitHub Actions can call the extractor after each BrightData job and upload raw files to GCS. When `ELT_RAW_GCS_BUCKET`, `ELT_BIGQUERY_PROJECT_ID`, and `ELT_BIGQUERY_DATASET` repository variables are configured, the IssueOps workflow also inserts one metadata-rich raw row into BigQuery.

The current BigQuery contract is intentionally simple: one raw object becomes one row with `raw_payload`, `source_run_id`, `raw_object_uri`, `payload_sha256`, and timestamps. Parsing into `raw_reviews_parsed`, `dim_facilities`, and `fact_reviews` is handled by SQL files in `sql/bigquery`.
