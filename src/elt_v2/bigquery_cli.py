from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from elt_v2.bigquery_loader import (
    TRANSFORM_SQL_FILES,
    build_csv_export_plan,
    build_compatibility_audit_plan,
    build_recent_review_serp_targets_sql,
    build_raw_load_plan,
    compatibility_audit_has_diff,
    export_table_to_gcs_csv,
    load_manifest_file,
    load_raw_payload_to_bigquery,
    render_sql_template,
    resolve_csv_export_destination_uri,
    replay_gcs_raw_object_to_bigquery,
    query_recent_review_serp_targets,
    run_compatibility_audit,
    run_sql_file,
    run_sql_files,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BigQuery helpers for the v2 ELT pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan-raw-load", help="Print a raw load plan from a manifest.")
    plan_parser.add_argument("--manifest", required=True, type=Path)
    plan_parser.add_argument("--project-id", required=True)
    plan_parser.add_argument("--dataset", required=True)
    plan_parser.add_argument("--source-uri")

    load_parser = subparsers.add_parser("load-raw", help="Load raw object data into BigQuery.")
    load_parser.add_argument("--manifest", required=True, type=Path)
    load_parser.add_argument("--project-id", required=True)
    load_parser.add_argument("--dataset", required=True)
    load_parser.add_argument("--payload-file", required=True, type=Path)
    load_parser.add_argument("--source-uri")

    replay_parser = subparsers.add_parser("replay-gcs-raw", help="Replay a GCS raw object into BigQuery.")
    replay_parser.add_argument("--raw-uri", required=True)
    replay_parser.add_argument("--manifest-uri")
    replay_parser.add_argument("--project-id", required=True)
    replay_parser.add_argument("--dataset", required=True)

    render_parser = subparsers.add_parser("render-sql", help="Render ${PROJECT_ID}/${DATASET} placeholders.")
    render_parser.add_argument("--sql-file", required=True, type=Path)
    render_parser.add_argument("--project-id", required=True)
    render_parser.add_argument("--dataset", required=True)

    run_parser = subparsers.add_parser("run-sql", help="Run a SQL file in BigQuery.")
    run_parser.add_argument("--sql-file", required=True, type=Path)
    run_parser.add_argument("--project-id", required=True)
    run_parser.add_argument("--dataset", required=True)

    run_all_parser = subparsers.add_parser("run-all-sql", help="Run managed SQL files in dependency order.")
    run_all_parser.add_argument("--project-id", required=True)
    run_all_parser.add_argument("--dataset", required=True)

    export_parser = subparsers.add_parser("export-csv", help="Export a BigQuery table to GCS as CSV.")
    export_parser.add_argument("--project-id", required=True)
    export_parser.add_argument("--dataset", required=True)
    export_parser.add_argument("--table", required=True)
    export_parser.add_argument("--destination-uri", default="")
    export_parser.add_argument("--gcs-bucket", default="")
    export_parser.add_argument("--legacy-output-path", default="")

    resolve_export_parser = subparsers.add_parser(
        "resolve-export-uri",
        help="Resolve a GCS CSV export URI from destination_uri or legacy output path.",
    )
    resolve_export_parser.add_argument("--destination-uri", default="")
    resolve_export_parser.add_argument("--gcs-bucket", default="")
    resolve_export_parser.add_argument("--legacy-output-path", default="")
    resolve_export_parser.add_argument("--table", required=True)

    audit_parser = subparsers.add_parser(
        "audit-csv-compat",
        help="Compare a legacy CSV with a BigQuery mart table using count and key-diff SQL.",
    )
    audit_parser.add_argument("--project-id", required=True)
    audit_parser.add_argument("--dataset", required=True)
    audit_parser.add_argument("--legacy-csv", required=True, type=Path)
    audit_parser.add_argument("--bq-table", required=True)
    audit_parser.add_argument("--legacy-key-column", action="append", required=True)
    audit_parser.add_argument("--bq-key-column", action="append")
    audit_parser.add_argument("--temp-table", default="_compat_legacy_csv_audit")
    audit_parser.add_argument("--sample-limit", type=int, default=20)
    audit_parser.add_argument("--output", type=Path)
    audit_parser.add_argument("--dry-run-sql", action="store_true")
    audit_parser.add_argument("--fail-on-diff", action="store_true")

    targets_parser = subparsers.add_parser(
        "build-serp-targets",
        help="Build a SERP target matrix from recent BigQuery reviews.",
    )
    targets_parser.add_argument("--project-id", required=True)
    targets_parser.add_argument("--dataset", required=True)
    targets_parser.add_argument("--days-back", type=int, required=True)
    targets_parser.add_argument("--row-limit", type=int)
    targets_parser.add_argument("--output", type=Path)
    targets_parser.add_argument("--dry-run-sql", action="store_true")

    list_parser = subparsers.add_parser("list-sql", help="List managed BigQuery SQL files.")
    list_parser.set_defaults(list_sql=True)

    args = parser.parse_args(argv)

    if args.command == "plan-raw-load":
        manifest = load_manifest_file(args.manifest)
        plan = build_raw_load_plan(
            manifest=manifest,
            project_id=args.project_id,
            dataset=args.dataset,
            source_uri=args.source_uri,
        )
        print(json.dumps(plan.__dict__, ensure_ascii=False, indent=2))
        return 0

    if args.command == "list-sql":
        print(json.dumps({"sql_files": TRANSFORM_SQL_FILES}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "load-raw":
        manifest = load_manifest_file(args.manifest)
        plan = build_raw_load_plan(
            manifest=manifest,
            project_id=args.project_id,
            dataset=args.dataset,
            source_uri=args.source_uri,
        )
        job_id = load_raw_payload_to_bigquery(plan, payload_file=args.payload_file)
        print(json.dumps({"job_id": job_id, "table_id": plan.table_id}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "replay-gcs-raw":
        result = replay_gcs_raw_object_to_bigquery(
            raw_uri=args.raw_uri,
            manifest_uri=args.manifest_uri,
            project_id=args.project_id,
            dataset=args.dataset,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "render-sql":
        print(
            render_sql_template(
                args.sql_file.read_text(encoding="utf-8"),
                project_id=args.project_id,
                dataset=args.dataset,
            )
        )
        return 0

    if args.command == "run-sql":
        job_id = run_sql_file(args.sql_file, project_id=args.project_id, dataset=args.dataset)
        print(json.dumps({"job_id": job_id}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-all-sql":
        results = run_sql_files(
            [Path(filename) for filename in TRANSFORM_SQL_FILES],
            project_id=args.project_id,
            dataset=args.dataset,
        )
        print(json.dumps({"jobs": results}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "export-csv":
        plan = build_csv_export_plan(
            project_id=args.project_id,
            dataset=args.dataset,
            table=args.table,
            destination_uri=args.destination_uri,
            gcs_bucket=args.gcs_bucket,
            legacy_output_path=args.legacy_output_path,
        )
        job_id = export_table_to_gcs_csv(plan)
        print(
            json.dumps(
                {"job_id": job_id, "table_id": plan.table_id, "destination_uri": plan.destination_uri},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "resolve-export-uri":
        destination_uri = resolve_csv_export_destination_uri(
            destination_uri=args.destination_uri,
            gcs_bucket=args.gcs_bucket,
            legacy_output_path=args.legacy_output_path,
            table=args.table,
        )
        print(json.dumps({"destination_uri": destination_uri}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "audit-csv-compat":
        plan = build_compatibility_audit_plan(
            project_id=args.project_id,
            dataset=args.dataset,
            legacy_csv_path=args.legacy_csv,
            bq_table=args.bq_table,
            legacy_key_columns=args.legacy_key_column,
            bq_key_columns=args.bq_key_column,
            temp_table=args.temp_table,
            sample_limit=args.sample_limit,
        )
        if args.dry_run_sql:
            from elt_v2.bigquery_loader import render_compatibility_audit_sql

            print(render_compatibility_audit_sql(plan))
            return 0

        result = run_compatibility_audit(plan)
        encoded = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        if args.fail_on_diff and compatibility_audit_has_diff(result):
            sys.stderr.write("compatibility audit found missing keys; see the JSON report for samples\n")
            return 1
        return 0

    if args.command == "build-serp-targets":
        if args.dry_run_sql:
            print(
                build_recent_review_serp_targets_sql(
                    project_id=args.project_id,
                    dataset=args.dataset,
                    days_back=args.days_back,
                    row_limit=args.row_limit,
                )
            )
            return 0

        matrix = query_recent_review_serp_targets(
            project_id=args.project_id,
            dataset=args.dataset,
            days_back=args.days_back,
            row_limit=args.row_limit,
        )
        encoded = json.dumps(matrix, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + "\n", encoding="utf-8")
            print(json.dumps({"items": len(matrix["include"]), "output": str(args.output)}, ensure_ascii=False, indent=2))
        else:
            print(encoded)
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
