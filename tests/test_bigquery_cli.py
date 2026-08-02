from __future__ import annotations

import json

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
