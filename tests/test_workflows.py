from __future__ import annotations

from pathlib import Path


def test_brightdata_extract_does_not_emit_raw_payload_as_job_output():
    workflow_text = Path(".github/workflows/brightdata-extract.yml").read_text(encoding="utf-8")

    assert "payload_json:" not in workflow_text
    assert "payload_json<<EOF" not in workflow_text
    assert "raw-ingest:" not in workflow_text
    assert "work/brightdata-result.json" in workflow_text
    assert "elt-raw-write" in workflow_text


def test_bigquery_export_workflow_uses_gcs_csv_destination():
    workflow_text = Path(".github/workflows/bigquery-export.yml").read_text(encoding="utf-8")

    assert "elt-bigquery export-csv" in workflow_text
    assert "--destination-uri" in workflow_text
    assert "GCP_SERVICE_ACCOUNT_JSON" in workflow_text
    assert "fact_reviews" in workflow_text
    assert "dim_facilities" in workflow_text


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
    assert "elt-bigquery load-raw" in workflow_text
    assert "ELT_RAW_GCS_BUCKET" in workflow_text


def test_serp_relevance_batch_workflow_builds_matrix_and_stores_raw_responses():
    workflow_text = Path(".github/workflows/serp-relevance-batch.yml").read_text(encoding="utf-8")

    assert "build-serp-items" in workflow_text
    assert "matrix: ${{ fromJson(needs.prepare.outputs.matrix) }}" in workflow_text
    assert "--dataset-kind serp_relevance" in workflow_text
    assert "elt-bigquery load-raw" in workflow_text
    assert "max-parallel" in workflow_text
    assert "START_FROM_BATCH" in workflow_text
    assert "effective_start_row" in workflow_text
    assert "target_source" in workflow_text
    assert "bigquery_recent_reviews" in workflow_text
    assert "build-serp-targets" in workflow_text
    assert "elt-bigquery run-all-sql" in workflow_text


def test_issue_ops_routes_reviews_relevance_to_serp_batch_after_dataset_extract():
    workflow_text = Path(".github/workflows/issue-ops-elt.yml").read_text(encoding="utf-8")

    assert "serp_relevance:" in workflow_text
    assert "uses: ./.github/workflows/serp-relevance-batch.yml" in workflow_text
    assert "needs: [parse, extract]" in workflow_text
    assert "workflow_type == 'reviews_recent_relevance'" in workflow_text
    assert "target_source: bigquery_recent_reviews" in workflow_text


def test_raw_object_replay_workflow_uses_gcs_raw_replay_cli():
    workflow_text = Path(".github/workflows/raw-object-replay.yml").read_text(encoding="utf-8")

    assert "elt-bigquery" in workflow_text
    assert "replay-gcs-raw" in workflow_text
    assert "--raw-uri" in workflow_text
    assert "GCP_SERVICE_ACCOUNT_JSON" in workflow_text
