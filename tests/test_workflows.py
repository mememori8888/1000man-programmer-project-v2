from __future__ import annotations

import json
from pathlib import Path


def test_brightdata_extract_does_not_emit_raw_payload_as_job_output():
    workflow_text = Path(".github/workflows/brightdata-extract.yml").read_text(encoding="utf-8")

    assert "payload_json:" not in workflow_text
    assert "payload_json<<EOF" not in workflow_text
    assert "raw-ingest:" not in workflow_text
    assert "Validate BrightData input CSV" in workflow_text
    assert "elt-brightdata validate-input" in workflow_text
    assert "Resolve input range" in workflow_text
    assert "work/brightdata-result.json" in workflow_text
    assert "elt-raw-write" in workflow_text
    assert workflow_text.count("elt-raw-write") == 1
    assert "optionally upload to GCS" in workflow_text
    assert "Ensure BigQuery raw tables" in workflow_text
    assert "sql/bigquery/001_create_raw_tables.sql" in workflow_text
    assert "Run BigQuery transforms" in workflow_text
    assert "elt-bigquery run-all-sql" in workflow_text
    assert "run_transform" in workflow_text
    assert "GITHUB_STEP_SUMMARY" in workflow_text


def test_bigquery_export_workflow_uses_gcs_csv_destination():
    workflow_text = Path(".github/workflows/bigquery-export.yml").read_text(encoding="utf-8")

    assert "elt-bigquery export-csv" in workflow_text
    assert "--destination-uri" in workflow_text
    assert "GCP_SERVICE_ACCOUNT_JSON" in workflow_text
    assert "fact_reviews" in workflow_text
    assert "dim_facilities" in workflow_text
    assert "fact_review_relevance_ranks" in workflow_text
    assert "GITHUB_STEP_SUMMARY" in workflow_text


def test_preflight_workflow_checks_required_runtime_settings():
    workflow_text = Path(".github/workflows/preflight.yml").read_text(encoding="utf-8")

    assert "BRIGHTDATA_API_TOKEN" in workflow_text
    assert "PRIVATE_REPO_PAT" in workflow_text
    assert "GCP_SERVICE_ACCOUNT_JSON" in workflow_text
    assert "ELT_RAW_GCS_BUCKET" in workflow_text
    assert "ELT_BIGQUERY_PROJECT_ID" in workflow_text
    assert "ELT_BIGQUERY_DATASET" in workflow_text
    assert "get_dataset" in workflow_text
    assert "mememori8888/googlemap" in workflow_text


def test_serp_smoke_workflow_uses_brightdata_serp_cli():
    workflow_text = Path(".github/workflows/serp-reviews-smoke.yml").read_text(encoding="utf-8")

    assert "elt-brightdata run-serp" in workflow_text
    assert "BRIGHTDATA_API_TOKEN" in workflow_text
    assert "--zone-name" in workflow_text
    assert "upload-artifact" in workflow_text


def test_serp_relevance_extract_workflow_stores_raw_response():
    workflow_text = Path(".github/workflows/serp-relevance-extract.yml").read_text(encoding="utf-8")

    assert "elt-brightdata run-serp" in workflow_text
    assert "--zone-name" in workflow_text
    assert "--dataset-kind serp_relevance" in workflow_text
    assert "sql/bigquery/001_create_raw_tables.sql" in workflow_text
    assert "elt-bigquery load-raw" in workflow_text
    assert "sql/bigquery/020_parse_raw_serp_responses.sql" in workflow_text
    assert "sql/bigquery/120_build_review_relevance_ranks.sql" in workflow_text
    assert "run_transform" in workflow_text
    assert "GITHUB_STEP_SUMMARY" in workflow_text
    assert "ELT_RAW_GCS_BUCKET" in workflow_text


def test_serp_relevance_batch_workflow_builds_matrix_and_stores_raw_responses():
    workflow_text = Path(".github/workflows/serp-relevance-batch.yml").read_text(encoding="utf-8")

    assert "build-serp-items" in workflow_text
    assert "matrix: ${{ fromJson(needs.prepare.outputs.matrix) }}" in workflow_text
    assert "--dataset-kind serp_relevance" in workflow_text
    assert "sql/bigquery/001_create_raw_tables.sql" in workflow_text
    assert "elt-bigquery load-raw" in workflow_text
    assert "max-parallel" in workflow_text
    assert "START_FROM_BATCH" in workflow_text
    assert "effective_start_row" in workflow_text
    assert "target_source" in workflow_text
    assert "bigquery_recent_reviews" in workflow_text
    assert "build-serp-targets" in workflow_text
    assert "elt-bigquery run-all-sql" in workflow_text
    assert "finalize:" in workflow_text
    assert "sql/bigquery/020_parse_raw_serp_responses.sql" in workflow_text
    assert "sql/bigquery/120_build_review_relevance_ranks.sql" in workflow_text
    assert "SERP relevance prepare" in workflow_text
    assert "SERP relevance finalize" in workflow_text


def test_issue_ops_routes_reviews_relevance_to_serp_batch_after_dataset_extract():
    workflow_text = Path(".github/workflows/issue-ops-elt.yml").read_text(encoding="utf-8")

    assert "config:" in workflow_text
    assert "reviews_recent_relevance requires these settings before paid extraction" in workflow_text
    assert "GCP_SERVICE_ACCOUNT_JSON" in workflow_text
    assert "ELT_RAW_GCS_BUCKET" in workflow_text
    assert "needs.config.outputs.valid == 'true'" in workflow_text
    assert "serp_relevance:" in workflow_text
    assert "uses: ./.github/workflows/serp-relevance-batch.yml" in workflow_text
    assert "needs: [parse, extract]" in workflow_text
    assert "workflow_type == 'reviews_recent_relevance'" in workflow_text
    assert "target_source: bigquery_recent_reviews" in workflow_text


def test_issue_ops_routes_generic_reviews_to_brightdata_extract():
    workflow_text = Path(".github/workflows/issue-ops-elt.yml").read_text(encoding="utf-8")

    assert "actions: read" in workflow_text
    assert "uses: ./.github/workflows/brightdata-extract.yml" in workflow_text
    assert "uses: ./.github/workflows/raw-elt-ingest.yml" not in workflow_text
    assert "needs.ingest" not in workflow_text
    assert "params.fid_file" in workflow_text
    assert "results/fid.csv" in workflow_text
    assert "params.start_line" in workflow_text
    assert "params.process_count" in workflow_text
    assert "workflow_type != 'reviews'" not in workflow_text


def test_brightdata_extract_supports_manual_reviews_fid_mode():
    workflow_text = Path(".github/workflows/brightdata-extract.yml").read_text(encoding="utf-8")

    assert "- reviews" in workflow_text
    assert '[ "${{ inputs.workflow_type }}" = "reviews" ]' in workflow_text


def test_issue_ops_report_distinguishes_success_failure_and_links_run():
    workflow_text = Path(".github/workflows/issue-ops-elt.yml").read_text(encoding="utf-8")

    assert "v2 ELT execution completed" in workflow_text
    assert "v2 ELT execution failed" in workflow_text
    assert "v2 ELT configuration check failed" in workflow_text
    assert "BrightData入力CSV検証" in workflow_text
    assert "context.runId" in workflow_text
    assert "VALIDATION_ERRORS" in workflow_text
    assert "process.env.CONFIG_ERRORS" in workflow_text


def test_raw_object_replay_workflow_uses_gcs_raw_replay_cli():
    workflow_text = Path(".github/workflows/raw-object-replay.yml").read_text(encoding="utf-8")

    assert "elt-bigquery" in workflow_text
    assert "sql/bigquery/001_create_raw_tables.sql" in workflow_text
    assert "replay-gcs-raw" in workflow_text
    assert "elt-bigquery run-all-sql" in workflow_text
    assert "run_transform" in workflow_text
    assert "--raw-uri" in workflow_text
    assert "GCP_SERVICE_ACCOUNT_JSON" in workflow_text
    assert "GITHUB_STEP_SUMMARY" in workflow_text


def test_raw_ingest_workflow_writes_step_summary():
    workflow_text = Path(".github/workflows/raw-elt-ingest.yml").read_text(encoding="utf-8")

    assert "Raw ELT ingest" in workflow_text
    assert "GITHUB_STEP_SUMMARY" in workflow_text
    assert "GCS raw object" in workflow_text
    assert "- serp_relevance" in workflow_text
    assert "sql/bigquery/001_create_raw_tables.sql" in workflow_text
    assert "elt-bigquery run-all-sql" in workflow_text
    assert "run_transform" in workflow_text


def test_compatibility_audit_workflow_uses_private_csv_and_bigquery_diff():
    workflow_text = Path(".github/workflows/compatibility-audit.yml").read_text(encoding="utf-8")

    assert "repository: mememori8888/googlemap" in workflow_text
    assert "PRIVATE_REPO_PAT" in workflow_text
    assert "GCP_SERVICE_ACCOUNT_JSON" in workflow_text
    assert "elt-bigquery audit-csv-compat" in workflow_text
    assert "--legacy-key-column" in workflow_text
    assert "compatibility-audit.json" in workflow_text
    assert "GITHUB_STEP_SUMMARY" in workflow_text


def test_webapp_uses_curated_public_file_presets():
    app_text = Path("docs/webapp/app.js").read_text(encoding="utf-8")
    index_text = Path("docs/webapp/index.html").read_text(encoding="utf-8")
    style_text = Path("docs/webapp/style.css").read_text(encoding="utf-8")
    presets = json.loads(Path("docs/webapp/file-presets.json").read_text(encoding="utf-8"))

    assert "file-presets.json" in app_text
    assert "api.github.com/repos" not in app_text
    assert 'list="sequentialInputFiles"' in index_text
    assert 'list="fidInputFiles"' in index_text
    assert 'list="reviewOutputFiles"' in index_text
    assert 'list="summaryOutputFiles"' in index_text
    assert 'id="fidFile"' in index_text
    assert 'id="startLine"' in index_text
    assert 'id="processCount"' in index_text
    assert 'id="workers"' in index_text
    assert "params.fid_file" not in app_text
    assert 'fid_file: fieldValue("fidFile")' in app_text
    assert 'start_line: fieldValue("startLine")' in app_text
    assert 'process_count: fieldValue("processCount")' in app_text
    assert 'workers: fieldValue("workers")' in app_text
    assert 'body[data-workflow="reviews"] .reviews-fields' in style_text
    assert 'body[data-workflow="reviews_recent_relevance"] .relevance-fields' in style_text
    assert presets["generated_by"] == "curated_public_v2_presets"
    assert any("sequential_input" in entry["purposes"] for entry in presets["results"])
    assert any("fid_input" in entry["purposes"] for entry in presets["results"])
    assert any("review_output" in entry["purposes"] for entry in presets["results"])
