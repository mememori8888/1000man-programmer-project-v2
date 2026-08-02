from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


COMMAND_TO_WORKFLOW = {
    "/run-facility": "facility",
    "/run-reviews-relevance": "reviews_recent_relevance",
    "/run-reviews-sequential": "reviews_sequential",
    "/run-reviews": "reviews",
}


@dataclass(frozen=True)
class IssueRequest:
    command: str
    workflow_type: str
    dataset_kind: str
    params: dict[str, Any]


def parse_issue_request(body: str) -> IssueRequest:
    command = _detect_command(body)
    workflow_type = COMMAND_TO_WORKFLOW[command]
    params = _extract_json_params(body)
    dataset_kind = "facilities" if workflow_type == "facility" else "reviews"
    return IssueRequest(
        command=command,
        workflow_type=workflow_type,
        dataset_kind=dataset_kind,
        params=params,
    )


def validate_issue_request(request: IssueRequest) -> list[str]:
    errors: list[str] = []
    params = request.params
    custom_settings = params.get("custom_settings")
    if custom_settings not in (None, "") and not isinstance(custom_settings, dict):
        errors.append("custom_settings must be an object")
        custom_settings = None

    if request.workflow_type == "reviews":
        _validate_private_csv_param(params, "fid_file", errors)
        _validate_private_csv_param(params, "csv_file", errors)
        if isinstance(custom_settings, dict):
            _validate_private_csv_param(custom_settings, "review_file", errors)
        if params.get("process_count") not in (None, ""):
            _require_positive_int(params, "process_count", errors)
        if params.get("start_line") not in (None, ""):
            _require_positive_int(params, "start_line", errors)
        if params.get("workers") not in (None, ""):
            _require_positive_int(params, "workers", errors)

    if request.workflow_type in {"reviews_sequential", "reviews_recent_relevance"}:
        for key in [
            "csv_file",
            "output_file",
            "days_back",
            "rows_per_batch",
            "api_batch_size",
            "max_wait_minutes",
            "dataset_id",
            "skip_column",
        ]:
            if params.get(key) in (None, ""):
                errors.append(f"{key} is required")

        _validate_private_csv_param(params, "csv_file", errors)
        _validate_private_csv_param(params, "output_file", errors)

        for key in [
            "days_back",
            "start_from_batch",
            "rows_per_batch",
            "max_parallel_jobs",
            "api_batch_size",
            "max_wait_minutes",
        ]:
            if params.get(key) not in (None, ""):
                _require_positive_int(params, key, errors)

        if params.get("max_parallel_jobs") not in (None, ""):
            try:
                if int(str(params["max_parallel_jobs"])) > 3:
                    errors.append("max_parallel_jobs must be 3 or less")
            except ValueError:
                pass

    if request.workflow_type == "reviews_recent_relevance":
        for key in ["relevance_rank_limit", "serp_max_workers", "serp_zone_name", "summary_file"]:
            if params.get(key) in (None, ""):
                errors.append(f"{key} is required")
        _validate_private_csv_param(params, "summary_file", errors)
        for key in ["relevance_rank_limit", "serp_max_workers"]:
            if params.get(key) not in (None, ""):
                _require_positive_int(params, key, errors)

    if request.workflow_type == "facility":
        _validate_private_csv_param(params, "csv_file", errors)
        if isinstance(custom_settings, dict):
            _validate_private_csv_param(custom_settings, "address_csv_path", errors)

    return errors


def to_payload_json(request: IssueRequest) -> str:
    payload = {
        "command": request.command,
        "workflow_type": request.workflow_type,
        "dataset_kind": request.dataset_kind,
        "params": request.params,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse a v2 IssueOps request body.")
    parser.add_argument("--body-file", required=True, type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)

    body = args.body_file.read_text(encoding="utf-8")
    request = parse_issue_request(body)
    errors = validate_issue_request(request)
    payload_json = to_payload_json(request)

    outputs = {
        "command": request.command,
        "workflow_type": request.workflow_type,
        "dataset_kind": request.dataset_kind,
        "params_json": json.dumps(request.params, ensure_ascii=False, sort_keys=True),
        "payload_json": payload_json,
        "valid": "true" if not errors else "false",
        "validation_errors": "\n".join(errors),
    }

    if args.github_output:
        _write_github_outputs(args.github_output, outputs)
    else:
        print(json.dumps(outputs, ensure_ascii=False, indent=2))

    return 0


def _detect_command(body: str) -> str:
    for command in COMMAND_TO_WORKFLOW:
        if command in body:
            return command
    raise ValueError("No supported /run-* command found")


def _extract_json_params(body: str) -> dict[str, Any]:
    match = re.search(r"```json\s*(.*?)\s*```", body, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return {}
    try:
        params = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON block: {exc}") from exc
    if not isinstance(params, dict):
        raise ValueError("JSON block must be an object")
    return params


def _require_positive_int(params: dict[str, Any], key: str, errors: list[str]) -> None:
    try:
        value = int(str(params[key]))
    except (TypeError, ValueError):
        errors.append(f"{key} must be an integer")
        return
    if value < 1:
        errors.append(f"{key} must be greater than 0")


def _validate_private_csv_param(params: dict[str, Any], key: str, errors: list[str]) -> None:
    value = params.get(key)
    if value in (None, ""):
        return
    if not isinstance(value, str):
        errors.append(f"{key} must be a string path")
        return

    normalized = value.replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    allowed_roots = {"settings", "results"}
    if (
        normalized.startswith("/")
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or not path.parts
        or path.parts[0] not in allowed_roots
    ):
        errors.append(f"{key} must be a safe CSV path under settings/ or results/")
        return
    if path.suffix.lower() != ".csv":
        errors.append(f"{key} must end with .csv")


def _write_github_outputs(path: Path, outputs: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as output:
        for key, value in outputs.items():
            if "\n" in value:
                output.write(f"{key}<<EOF\n{value}\nEOF\n")
            else:
                output.write(f"{key}={value}\n")


if __name__ == "__main__":
    raise SystemExit(main())
