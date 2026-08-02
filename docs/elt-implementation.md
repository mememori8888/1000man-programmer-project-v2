# ELT implementation notes

This project moves heavy matching and deduplication out of Python and into BigQuery.

## Current implemented boundary

- `elt-raw-write` validates a BrightData `.json` or `.csv` export.
- It writes the untouched payload under a deterministic raw object path.
- It writes a sidecar manifest with `source_run_id`, SHA-256, byte size, object name, and extraction time.
- The same object can be written locally for tests or uploaded to GCS when `google-cloud-storage` is installed.

## Next boundary

GitHub Actions should call the extractor after each BrightData job and upload raw files to GCS. A later workflow step should load those objects into BigQuery raw tables and run the SQL transforms in `sql/bigquery`.
