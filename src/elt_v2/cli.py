from __future__ import annotations

import argparse
import json
from pathlib import Path

from elt_v2.raw_writer import (
    build_raw_object,
    upload_raw_object_to_gcs,
    write_raw_object_local,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write BrightData raw JSON/CSV output to local storage or GCS."
    )
    parser.add_argument("--input", required=True, type=Path, help="Raw .json or .csv file")
    parser.add_argument("--source-run-id", required=True, help="GitHub run id or equivalent")
    parser.add_argument(
        "--dataset-kind",
        required=True,
        choices=["reviews", "facilities", "serp_relevance"],
        help="Raw dataset category",
    )
    parser.add_argument("--local-output-root", type=Path, help="Write under this local root")
    parser.add_argument("--gcs-bucket", help="Upload to this GCS bucket")
    args = parser.parse_args(argv)

    if not args.local_output_root and not args.gcs_bucket:
        parser.error("one of --local-output-root or --gcs-bucket is required")

    raw_object = build_raw_object(
        input_path=args.input,
        source_run_id=args.source_run_id,
        dataset_kind=args.dataset_kind,
    )

    results: dict[str, str | dict] = {"manifest": raw_object.manifest}

    if args.local_output_root:
        local_path = write_raw_object_local(raw_object, args.local_output_root)
        results["local_path"] = str(local_path)

    if args.gcs_bucket:
        results["gcs_uri"] = upload_raw_object_to_gcs(raw_object, args.gcs_bucket)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
