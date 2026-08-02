from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from elt_v2.brightdata import (
    BrightDataDatasetClient,
    BrightDataSerpClient,
    build_dataset_items_from_csv,
    build_serp_relevance_items_from_csv,
    validate_dataset_csv,
    write_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BrightData extract helpers for v2 ELT.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build-items", help="Build BrightData input items from CSV.")
    build_parser.add_argument("--csv-file", required=True, type=Path)
    build_parser.add_argument("--workflow-type", required=True)
    build_parser.add_argument("--output", required=True, type=Path)
    build_parser.add_argument("--days-back", type=int, default=10)
    build_parser.add_argument("--skip-column", nargs="?", const="", default="web")
    build_parser.add_argument("--start-row", type=int, default=1)
    build_parser.add_argument("--row-limit", type=int)
    build_parser.add_argument("--query", default="")

    validate_parser = subparsers.add_parser("validate-input", help="Validate CSV input before a paid Dataset API run.")
    validate_parser.add_argument("--csv-file", required=True, type=Path)
    validate_parser.add_argument("--workflow-type", required=True)
    validate_parser.add_argument("--days-back", type=int, default=10)
    validate_parser.add_argument("--skip-column", nargs="?", const="", default="web")
    validate_parser.add_argument("--start-row", type=int, default=1)
    validate_parser.add_argument("--row-limit", type=int)
    validate_parser.add_argument("--query", default="")
    validate_parser.add_argument("--output", type=Path)

    serp_items_parser = subparsers.add_parser("build-serp-items", help="Build SERP relevance input items from CSV.")
    serp_items_parser.add_argument("--csv-file", required=True, type=Path)
    serp_items_parser.add_argument("--output", required=True, type=Path)
    serp_items_parser.add_argument("--skip-column", nargs="?", const="", default="web")
    serp_items_parser.add_argument("--start-row", type=int, default=1)
    serp_items_parser.add_argument("--row-limit", type=int)

    dataset_parser = subparsers.add_parser("run-dataset", help="Run BrightData Dataset API.")
    dataset_parser.add_argument("--dataset-id", required=True)
    dataset_parser.add_argument("--items-file", required=True, type=Path)
    dataset_parser.add_argument("--output", required=True, type=Path)
    dataset_parser.add_argument("--api-token", default=os.getenv("BRIGHTDATA_API_TOKEN"))
    dataset_parser.add_argument("--max-wait-minutes", type=int, default=90)
    dataset_parser.add_argument("--poll-interval-seconds", type=int, default=15)

    serp_parser = subparsers.add_parser("run-serp", help="Run one BrightData SERP request.")
    serp_parser.add_argument("--zone-name", default=os.getenv("BRIGHTDATA_ZONE_NAME") or "serp_api2")
    serp_parser.add_argument("--url", required=True)
    serp_parser.add_argument("--output", required=True, type=Path)
    serp_parser.add_argument("--api-token", default=os.getenv("BRIGHTDATA_API_TOKEN"))
    serp_parser.add_argument("--format", default="json", choices=["json", "raw"])

    args = parser.parse_args(argv)

    if args.command == "build-items":
        items = build_dataset_items_from_csv(
            csv_path=args.csv_file,
            workflow_type=args.workflow_type,
            days_back=args.days_back,
            skip_column=args.skip_column,
            start_row=args.start_row,
            row_limit=args.row_limit,
            query=args.query,
        )
        write_json(args.output, items)
        print(json.dumps({"items": len(items), "output": str(args.output)}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-input":
        validation = validate_dataset_csv(
            csv_path=args.csv_file,
            workflow_type=args.workflow_type,
            days_back=args.days_back,
            skip_column=args.skip_column,
            start_row=args.start_row,
            row_limit=args.row_limit,
            query=args.query,
        )
        encoded = json.dumps(validation.__dict__, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        return 0

    if args.command == "build-serp-items":
        items = build_serp_relevance_items_from_csv(
            csv_path=args.csv_file,
            skip_column=args.skip_column,
            start_row=args.start_row,
            row_limit=args.row_limit,
        )
        write_json(args.output, {"include": items})
        print(json.dumps({"items": len(items), "output": str(args.output)}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-dataset":
        items = json.loads(args.items_file.read_text(encoding="utf-8-sig"))
        client = BrightDataDatasetClient(args.api_token)
        result = client.run_snapshot(
            dataset_id=args.dataset_id,
            items=items,
            max_wait_minutes=args.max_wait_minutes,
            poll_interval_seconds=args.poll_interval_seconds,
        )
        write_json(
            args.output,
            {
                "snapshot_id": result.snapshot_id,
                "data": result.data,
            },
        )
        print(json.dumps({"snapshot_id": result.snapshot_id, "output": str(args.output)}, indent=2))
        return 0

    if args.command == "run-serp":
        client = BrightDataSerpClient(args.api_token)
        result = client.request(
            zone_name=args.zone_name,
            url=args.url,
            response_format=args.format,
        )
        if args.format == "raw":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(str(result), encoding="utf-8")
        else:
            write_json(args.output, result)
        print(json.dumps({"output": str(args.output)}, indent=2))
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
