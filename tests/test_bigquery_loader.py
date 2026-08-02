from __future__ import annotations

import json

import pytest

from elt_v2.bigquery_loader import (
    TRANSFORM_SQL_FILES,
    build_csv_export_plan,
    build_raw_load_plan,
    build_raw_table_row,
    load_manifest_file,
    parse_gcs_uri,
    render_sql_template,
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


def test_transform_sql_file_registry_includes_parse_steps():
    assert "sql/bigquery/010_parse_raw_reviews.sql" in TRANSFORM_SQL_FILES
    assert "sql/bigquery/011_parse_raw_facilities.sql" in TRANSFORM_SQL_FILES
    assert TRANSFORM_SQL_FILES.index("sql/bigquery/010_parse_raw_reviews.sql") < TRANSFORM_SQL_FILES.index(
        "sql/bigquery/101_deduplicate_reviews.sql"
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
