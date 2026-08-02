from __future__ import annotations

import json

import pytest

from elt_v2.bigquery_loader import (
    TRANSFORM_SQL_FILES,
    build_compatibility_audit_plan,
    build_csv_export_plan,
    build_recent_review_serp_targets_sql,
    build_raw_load_plan,
    build_raw_table_row,
    compatibility_audit_has_diff,
    load_manifest_file,
    parse_gcs_uri,
    render_compatibility_audit_sql,
    render_sql_template,
    resolve_csv_export_destination_uri,
    run_sql_files,
)


def test_builds_reviews_raw_load_plan_from_manifest():
    manifest = {
        "source_run_id": "run-1",
        "dataset_kind": "reviews",
        "object_name": "raw/reviews/2026/08/03/source_run_id=run-1/payload.json",
        "bucket": "raw-bucket",
        "sha256": "abc123",
        "extracted_at": "2026-08-03T00:00:00Z",
    }

    plan = build_raw_load_plan(
        manifest=manifest,
        project_id="project-123",
        dataset="brightdata_raw",
    )

    assert plan.table_id == "project-123.brightdata_raw.raw_reviews"
    assert plan.source_uri == "gs://raw-bucket/raw/reviews/2026/08/03/source_run_id=run-1/payload.json"
    assert plan.payload_sha256 == "abc123"


def test_builds_facilities_raw_load_plan_with_explicit_source_uri():
    manifest = {
        "source_run_id": "run-2",
        "dataset_kind": "facilities",
        "object_name": "raw/facilities/file.csv",
        "sha256": "def456",
        "extracted_at": "2026-08-03T00:00:00Z",
    }

    plan = build_raw_load_plan(
        manifest=manifest,
        project_id="project-123",
        dataset="brightdata_raw",
        source_uri="gs://another-bucket/raw/facilities/file.csv",
    )

    assert plan.table == "raw_facilities"
    assert plan.source_uri == "gs://another-bucket/raw/facilities/file.csv"


def test_builds_serp_relevance_raw_load_plan():
    manifest = {
        "source_run_id": "serp-1",
        "dataset_kind": "serp_relevance",
        "object_name": "raw/serp_relevance/file.json",
        "sha256": "abc123",
        "extracted_at": "2026-08-03T00:00:00Z",
    }

    plan = build_raw_load_plan(
        manifest=manifest,
        project_id="project-123",
        dataset="brightdata_raw",
        source_uri="gs://raw-bucket/raw/serp_relevance/file.json",
    )

    assert plan.table_id == "project-123.brightdata_raw.raw_serp_responses"


def test_rejects_non_gcs_uri():
    manifest = {
        "source_run_id": "run-1",
        "dataset_kind": "reviews",
        "gcs_uri": "file:///tmp/payload.json",
        "extracted_at": "2026-08-03T00:00:00Z",
    }

    with pytest.raises(ValueError, match="gs://"):
        build_raw_load_plan(manifest=manifest, project_id="project-123", dataset="brightdata_raw")


def test_renders_sql_template():
    sql = "select * from `${PROJECT_ID}.${DATASET}.raw_reviews`"

    assert (
        render_sql_template(sql, project_id="project-123", dataset="brightdata_raw")
        == "select * from `project-123.brightdata_raw.raw_reviews`"
    )


def test_builds_raw_table_row():
    manifest = {
        "source_run_id": "run-1",
        "dataset_kind": "reviews",
        "bucket": "raw-bucket",
        "object_name": "raw/reviews/file.json",
        "sha256": "abc123",
        "extracted_at": "2026-08-03T00:00:00Z",
    }
    plan = build_raw_load_plan(manifest=manifest, project_id="project-123", dataset="brightdata_raw")

    row = build_raw_table_row(plan=plan, raw_payload='{"hello":"world"}')

    assert row == {
        "source_run_id": "run-1",
        "raw_object_uri": "gs://raw-bucket/raw/reviews/file.json",
        "raw_payload": '{"hello":"world"}',
        "source_system": "brightdata",
        "extracted_at": "2026-08-03T00:00:00Z",
        "payload_sha256": "abc123",
        "dataset_kind": "reviews",
    }


def test_plan_can_be_json_serialized():
    manifest = {
        "source_run_id": "run-1",
        "dataset_kind": "reviews",
        "bucket": "raw-bucket",
        "object_name": "raw/reviews/file.json",
        "extracted_at": "2026-08-03T00:00:00Z",
    }

    plan = build_raw_load_plan(manifest=manifest, project_id="project-123", dataset="brightdata_raw")

    assert json.loads(json.dumps(plan.__dict__))["table"] == "raw_reviews"


def test_load_manifest_file_accepts_utf8_bom(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"dataset_kind":"reviews"}', encoding="utf-8-sig")

    assert load_manifest_file(manifest_path)["dataset_kind"] == "reviews"


def test_parse_gcs_uri():
    assert parse_gcs_uri("gs://raw-bucket/raw/reviews/file%20one.json") == (
        "raw-bucket",
        "raw/reviews/file one.json",
    )

    with pytest.raises(ValueError, match="gs://"):
        parse_gcs_uri("https://example.com/file.json")

    with pytest.raises(ValueError, match="bucket and object"):
        parse_gcs_uri("gs://raw-bucket")


def test_builds_csv_export_plan():
    plan = build_csv_export_plan(
        project_id="project-123",
        dataset="brightdata_raw",
        table="fact_reviews",
        destination_uri="gs://export-bucket/reviews/fact_reviews-*.csv",
    )

    assert plan.table_id == "project-123.brightdata_raw.fact_reviews"
    assert plan.destination_uri == "gs://export-bucket/reviews/fact_reviews-*.csv"


def test_resolves_legacy_csv_export_destination_uri():
    assert (
        resolve_csv_export_destination_uri(
            gcs_bucket="export-bucket",
            legacy_output_path="results/dental_reviews.csv",
            table="fact_reviews",
        )
        == "gs://export-bucket/exports/results/dental_reviews-*.csv"
    )
    assert (
        resolve_csv_export_destination_uri(gcs_bucket="export-bucket", legacy_output_path="summary", table="fact_reviews")
        == "gs://export-bucket/exports/summary-*.csv"
    )


def test_rejects_unsafe_legacy_csv_export_path():
    with pytest.raises(ValueError, match="not safe"):
        resolve_csv_export_destination_uri(
            gcs_bucket="export-bucket",
            legacy_output_path="../secret.csv",
            table="fact_reviews",
        )


def test_builds_compatibility_audit_sql(tmp_path):
    legacy_csv = tmp_path / "legacy.csv"
    legacy_csv.write_text("review_id,facility_id\nr1,f1\n", encoding="utf-8")

    plan = build_compatibility_audit_plan(
        project_id="project-123",
        dataset="brightdata_raw",
        legacy_csv_path=legacy_csv,
        bq_table="fact_reviews",
        legacy_key_columns=["review_id", "facility_id"],
        bq_key_columns=["review_id", "facility_id"],
        temp_table="_compat_test",
        sample_limit=5,
    )
    sql = render_compatibility_audit_sql(plan)

    assert plan.temp_table_id == "project-123.brightdata_raw._compat_test"
    assert "`project-123.brightdata_raw._compat_test`" in sql
    assert "`project-123.brightdata_raw.fact_reviews`" in sql
    assert "missing_in_bq_count" in sql
    assert "missing_in_legacy_count" in sql
    assert "limit 5" in sql


def test_detects_compatibility_audit_diff():
    assert compatibility_audit_has_diff({"missing_in_bq_count": 1, "missing_in_legacy_count": 0})
    assert compatibility_audit_has_diff({"missing_in_bq_count": 0, "missing_in_legacy_count": 2})
    assert not compatibility_audit_has_diff({"missing_in_bq_count": 0, "missing_in_legacy_count": 0})


def test_builds_recent_review_serp_targets_sql():
    sql = build_recent_review_serp_targets_sql(
        project_id="project-123",
        dataset="brightdata_raw",
        days_back=30,
        row_limit=10,
    )

    assert "`project-123.brightdata_raw.fact_reviews`" in sql
    assert "`project-123.brightdata_raw.dim_facilities`" in sql
    assert "`project-123.brightdata_raw.raw_reviews_parsed`" in sql
    assert "interval 30 day" in sql
    assert "limit 10" in sql
    assert "google_map_url" in sql
    assert "$.input.url" in sql
    assert "left join `project-123.brightdata_raw.dim_facilities`" in sql
    assert "left join review_input_urls" in sql


def test_rejects_non_gcs_csv_export_uri():
    with pytest.raises(ValueError, match="gs://"):
        build_csv_export_plan(
            project_id="project-123",
            dataset="brightdata_raw",
            table="fact_reviews",
            destination_uri="file:///tmp/fact_reviews.csv",
        )

    with pytest.raises(ValueError, match="csv"):
        build_csv_export_plan(
            project_id="project-123",
            dataset="brightdata_raw",
            table="fact_reviews",
            destination_uri="gs://export-bucket/reviews/fact_reviews.json",
        )

    with pytest.raises(ValueError, match="csv"):
        build_csv_export_plan(
            project_id="project-123",
            dataset="brightdata_raw",
            table="fact_reviews",
            destination_uri="gs://export-bucket/reviews/fact_reviews-*.json",
        )


def test_transform_sql_file_registry_includes_parse_steps():
    assert "sql/bigquery/010_parse_raw_reviews.sql" in TRANSFORM_SQL_FILES
    assert "sql/bigquery/011_parse_raw_facilities.sql" in TRANSFORM_SQL_FILES
    assert "sql/bigquery/020_parse_raw_serp_responses.sql" in TRANSFORM_SQL_FILES
    assert "sql/bigquery/120_build_review_relevance_ranks.sql" in TRANSFORM_SQL_FILES
    assert TRANSFORM_SQL_FILES.index("sql/bigquery/010_parse_raw_reviews.sql") < TRANSFORM_SQL_FILES.index(
        "sql/bigquery/101_deduplicate_reviews.sql"
    )
    assert TRANSFORM_SQL_FILES.index("sql/bigquery/020_parse_raw_serp_responses.sql") < TRANSFORM_SQL_FILES.index(
        "sql/bigquery/120_build_review_relevance_ranks.sql"
    )


def test_run_sql_files_preserves_order(monkeypatch):
    calls = []

    def fake_run_sql_file(path, *, project_id, dataset):
        calls.append((str(path), project_id, dataset))
        return f"job-{len(calls)}"

    monkeypatch.setattr("elt_v2.bigquery_loader.run_sql_file", fake_run_sql_file)

    results = run_sql_files(
        [TRANSFORM_SQL_FILES[0], TRANSFORM_SQL_FILES[1]],
        project_id="project-123",
        dataset="brightdata_raw",
    )

    assert results == [
        {"sql_file": TRANSFORM_SQL_FILES[0], "job_id": "job-1"},
        {"sql_file": TRANSFORM_SQL_FILES[1], "job_id": "job-2"},
    ]
    assert calls == [
        (TRANSFORM_SQL_FILES[0], "project-123", "brightdata_raw"),
        (TRANSFORM_SQL_FILES[1], "project-123", "brightdata_raw"),
    ]
