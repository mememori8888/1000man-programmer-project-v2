from __future__ import annotations

from pathlib import Path

from elt_v2.bigquery_loader import TRANSFORM_SQL_FILES, render_sql_template


def test_all_registered_sql_files_exist_and_render():
    for filename in TRANSFORM_SQL_FILES:
        path = Path(filename)
        assert path.exists(), filename
        rendered = render_sql_template(
            path.read_text(encoding="utf-8"),
            project_id="project-123",
            dataset="brightdata_raw",
        )
        assert "${PROJECT_ID}" not in rendered
        assert "${DATASET}" not in rendered
        assert "project-123.brightdata_raw" in rendered


def test_bigquery_transform_workflow_exposes_registered_sql_files():
    workflow_text = Path(".github/workflows/bigquery-transform.yml").read_text(encoding="utf-8")
    options = [
        line.strip().removeprefix("- ")
        for line in workflow_text.splitlines()
        if line.strip().startswith("- sql/bigquery/")
    ]
    all_options = [
        line.strip().removeprefix("- ")
        for line in workflow_text.splitlines()
        if line.strip() == "- all"
    ]

    assert all_options == ["all"]
    assert options == TRANSFORM_SQL_FILES


def test_review_parser_keeps_input_facility_keys():
    sql = Path("sql/bigquery/010_parse_raw_reviews.sql").read_text(encoding="utf-8")

    assert "$.input.facility_id" in sql
    assert "$.input.fid" in sql
    assert "$.input.gid" in sql
    assert "$.fid" in sql


def test_serp_parser_uses_request_facility_id_from_envelope():
    sql = Path("sql/bigquery/020_parse_raw_serp_responses.sql").read_text(encoding="utf-8")

    assert "$.request.facility_id" in sql
    assert "request_facility_id" in sql
    assert "nullif(request_facility_id, '')" in sql
    assert sql.index("nullif(request_facility_id, '')") < sql.index("nullif(json_value(item_json, '$.url'), '')")


def test_mart_transforms_preserve_bigquery_physical_design():
    review_stage_sql = Path("sql/bigquery/010_parse_raw_reviews.sql").read_text(encoding="utf-8").lower()
    dim_sql = Path("sql/bigquery/011_parse_raw_facilities.sql").read_text(encoding="utf-8").lower()
    serp_stage_sql = Path("sql/bigquery/020_parse_raw_serp_responses.sql").read_text(encoding="utf-8").lower()
    reviews_sql = Path("sql/bigquery/101_deduplicate_reviews.sql").read_text(encoding="utf-8").lower()
    ranks_sql = Path("sql/bigquery/120_build_review_relevance_ranks.sql").read_text(encoding="utf-8").lower()

    assert "partition by date(extracted_at)" in review_stage_sql
    assert "cluster by facility_id, review_id" in review_stage_sql
    assert "cluster by facility_type, facility_id" in dim_sql
    assert "min(first_seen_at) over" in dim_sql
    assert "facility_first_seen_at as first_seen_at" in dim_sql
    assert "max(updated_at) over" in dim_sql
    assert "facility_updated_at as updated_at" in dim_sql
    assert "partition by date(extracted_at)" in serp_stage_sql
    assert "cluster by facility_id, review_id" in serp_stage_sql
    assert "partition by review_date" in reviews_sql
    assert "cluster by facility_id, review_id" in reviews_sql
    assert "cluster by facility_id, review_id" in ranks_sql


def test_sql_files_label_dwh_layers_without_changing_public_marts():
    raw_sql = Path("sql/bigquery/001_create_raw_tables.sql").read_text(encoding="utf-8").lower()
    review_stage_sql = Path("sql/bigquery/010_parse_raw_reviews.sql").read_text(encoding="utf-8").lower()
    serp_stage_sql = Path("sql/bigquery/020_parse_raw_serp_responses.sql").read_text(encoding="utf-8").lower()
    dim_sql = Path("sql/bigquery/011_parse_raw_facilities.sql").read_text(encoding="utf-8").lower()
    reviews_sql = Path("sql/bigquery/101_deduplicate_reviews.sql").read_text(encoding="utf-8").lower()
    ranks_sql = Path("sql/bigquery/120_build_review_relevance_ranks.sql").read_text(encoding="utf-8").lower()

    assert "raw layer" in raw_sql
    assert "staging layer" in review_stage_sql
    assert "staging layer" in serp_stage_sql
    assert "mart layer" in dim_sql
    assert "mart layer" in reviews_sql
    assert "mart layer" in ranks_sql

    assert "create or replace table `${project_id}.${dataset}.dim_facilities`" in dim_sql
    assert "create or replace table `${project_id}.${dataset}.fact_reviews`" in reviews_sql
    assert "create or replace table `${project_id}.${dataset}.fact_review_relevance_ranks`" in ranks_sql
