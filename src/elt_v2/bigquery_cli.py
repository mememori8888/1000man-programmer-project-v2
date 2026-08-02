from __future__ import annotations

import argparse
import json
from pathlib import Path

from elt_v2.bigquery_loader import (
    TRANSFORM_SQL_FILES,
    build_raw_load_plan,
    load_manifest_file,
    load_raw_payload_to_bigquery,
    render_sql_template,
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

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
