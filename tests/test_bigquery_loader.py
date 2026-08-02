from __future__ import annotations

import json

import pytest

from elt_v2.bigquery_loader import (
    build_raw_load_plan,
    build_raw_table_row,
    load_manifest_file,
    render_sql_template,
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
