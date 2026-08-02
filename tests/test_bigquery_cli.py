from __future__ import annotations

import json
from pathlib import Path

from elt_v2 import bigquery_cli


def test_audit_csv_compat_can_fail_after_writing_report(monkeypatch, tmp_path):
    legacy_csv = tmp_path / "legacy.csv"
    legacy_csv.write_text("review_id\nr1\n", encoding="utf-8")
    output_path = tmp_path / "audit.json"

    def fake_run_compatibility_audit(plan):
        return {
            "legacy_csv": str(plan.legacy_csv_path),
            "legacy_temp_table": plan.temp_table_id,
            "bq_table": plan.bq_table_id,
            "legacy_key_columns": list(plan.legacy_key_columns),
            "bq_key_columns": list(plan.bq_key_columns),
            "legacy_row_count": 1,
            "bq_row_count": 0,
            "legacy_distinct_key_count": 1,
            "bq_distinct_key_count": 0,
            "missing_in_bq_count": 1,
            "missing_in_legacy_count": 0,
            "missing_in_bq_sample": ["r1"],
            "missing_in_legacy_sample": [],
        }

    monkeypatch.setattr(bigquery_cli, "run_compatibility_audit", fake_run_compatibility_audit)

    exit_code = bigquery_cli.main(
        [
            "audit-csv-compat",
            "--project-id",
            "project-123",
            "--dataset",
            "brightdata_raw",
            "--legacy-csv",
            str(legacy_csv),
            "--bq-table",
            "fact_reviews",
            "--legacy-key-column",
            "review_id",
            "--output",
            str(output_path),
            "--fail-on-diff",
        ]
    )

    assert exit_code == 1
    assert json.loads(output_path.read_text(encoding="utf-8"))["missing_in_bq_count"] == 1


def test_dry_run_all_sql_cli_uses_registered_sql_files(monkeypatch, capsys):
    calls = []

    def fake_dry_run_sql_files(paths, *, project_id, dataset):
        calls.extend(str(path) for path in paths)
        return [
            {"sql_file": str(path), "job_id": f"dry-{index}", "total_bytes_processed": index}
            for index, path in enumerate(paths, start=1)
        ]

    monkeypatch.setattr(bigquery_cli, "dry_run_sql_files", fake_dry_run_sql_files)

    exit_code = bigquery_cli.main(
        [
            "dry-run-all-sql",
            "--project-id",
            "project-123",
            "--dataset",
            "brightdata_raw",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert calls == [str(Path(filename)) for filename in bigquery_cli.TRANSFORM_SQL_FILES]
    assert output["jobs"][0] == {
        "sql_file": str(Path(bigquery_cli.TRANSFORM_SQL_FILES[0])),
        "job_id": "dry-1",
        "total_bytes_processed": 1,
    }


def test_build_serp_targets_dry_run_cli_prints_sql(capsys):
    exit_code = bigquery_cli.main(
        [
            "build-serp-targets",
            "--project-id",
            "project-123",
            "--dataset",
            "brightdata_raw",
            "--days-back",
            "14",
            "--row-limit",
            "5",
            "--dry-run-sql",
        ]
    )

    sql = capsys.readouterr().out
    assert exit_code == 0
    assert "`project-123.brightdata_raw.fact_reviews`" in sql
    assert "interval 14 day" in sql
    assert "limit 5" in sql
