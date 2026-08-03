from __future__ import annotations

from pathlib import Path


def test_readme_links_release_evidence_checklist():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "docs/demo-compatibility-audit.md" in readme
    assert "release evidence checklist" in readme
    assert "raw payload / manifest" in readme
    assert "compatibility-audit.json" in readme


def test_demo_compatibility_doc_lists_required_release_evidence():
    doc = Path("docs/demo-compatibility-audit.md").read_text(encoding="utf-8")

    assert "Release evidence checklist" in doc
    assert "v2 ELT preflight" in doc
    assert "work-bigquery-dry-run.json" in doc
    assert "raw payload GCS URI" in doc
    assert "raw manifest GCS URI" in doc
    assert "fact_reviews" in doc
    assert "dim_facilities" in doc
    assert "fact_review_relevance_ranks" in doc
    assert "run_transform: true" in doc
    assert "fail_on_diff: true" in doc
    assert "compatibility-audit.json" in doc
    assert "旧ファイルや旧 workflow" in doc
    assert "elt_v2.evidence_cli template" in doc
    assert "elt_v2.evidence_cli validate" in doc
    assert "v2 release evidence validation" in doc
    assert "release-evidence-validation" in doc


def test_bigquery_sql_guide_explains_all_sql_files_for_beginners():
    doc = Path("docs/bigquery-sql-guide.md").read_text(encoding="utf-8")

    assert "SQL 初心者向け解説" in doc
    assert "raw layer" in doc
    assert "staging layer" in doc
    assert "mart layer" in doc
    for filename in [
        "001_create_raw_tables.sql",
        "002_create_mart_tables.sql",
        "010_parse_raw_reviews.sql",
        "011_parse_raw_facilities.sql",
        "020_parse_raw_serp_responses.sql",
        "101_deduplicate_reviews.sql",
        "120_build_review_relevance_ranks.sql",
    ]:
        assert filename in doc
    for concept in [
        "coalesce",
        "unnest",
        "row_number()",
        "partition by",
        "cluster by",
        "SCD Type 1",
    ]:
        assert concept in doc
