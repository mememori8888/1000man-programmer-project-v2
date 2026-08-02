from __future__ import annotations

from dataclasses import dataclass
from typing import Any


REQUIRED_TOP_LEVEL_KEYS = (
    "preflight",
    "issueops",
    "extract",
    "load_transform",
    "exports",
    "compatibility_audit",
)

REQUIRED_EXPORT_TABLES = ("fact_reviews", "dim_facilities", "fact_review_relevance_ranks")
REQUIRED_ISSUE_COMMANDS = (
    "/run-facility",
    "/run-reviews",
    "/run-reviews-sequential",
    "/run-reviews-relevance",
)


@dataclass(frozen=True)
class EvidenceValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


def build_evidence_template() -> dict[str, Any]:
    return {
        "preflight": {
            "run_id": "",
            "summary_url": "",
            "dry_run_artifact": "work-bigquery-dry-run.json",
        },
        "issueops": {
            "issue_url": "",
            "approved_comment": "/承認",
            "commands": list(REQUIRED_ISSUE_COMMANDS),
        },
        "extract": {
            "run_id": "",
            "raw_payload_gcs_uri": "",
            "raw_manifest_gcs_uri": "",
        },
        "load_transform": {
            "run_id": "",
            "raw_load_job_id": "",
            "transform_run_id": "",
        },
        "exports": {
            table: {
                "run_id": "",
                "gcs_uri": "",
            }
            for table in REQUIRED_EXPORT_TABLES
        },
        "compatibility_audit": {
            "run_id": "",
            "artifact": "compatibility-audit.json",
            "run_transform": True,
            "fail_on_diff": True,
        },
        "exceptions": [],
    }


def validate_evidence(payload: dict[str, Any]) -> EvidenceValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in payload:
            errors.append(f"{key} is required")

    _require_text(payload, ("preflight", "run_id"), errors)
    _require_text(payload, ("preflight", "summary_url"), errors)
    _require_exact_text(payload, ("preflight", "dry_run_artifact"), "work-bigquery-dry-run.json", errors)

    _require_text(payload, ("issueops", "issue_url"), errors)
    _require_exact_text(payload, ("issueops", "approved_comment"), "/承認", errors)
    commands = _get(payload, ("issueops", "commands"))
    if not isinstance(commands, list):
        errors.append("issueops.commands must be a list")
    else:
        missing_commands = [command for command in REQUIRED_ISSUE_COMMANDS if command not in commands]
        for command in missing_commands:
            errors.append(f"issueops.commands must include {command}")

    _require_text(payload, ("extract", "run_id"), errors)
    _require_gcs_uri(payload, ("extract", "raw_payload_gcs_uri"), errors)
    _require_gcs_uri(payload, ("extract", "raw_manifest_gcs_uri"), errors)

    _require_text(payload, ("load_transform", "run_id"), errors)
    _require_text(payload, ("load_transform", "raw_load_job_id"), errors)

    transform_run_id = _get(payload, ("load_transform", "transform_run_id"))
    if not _is_non_empty_text(transform_run_id):
        warnings.append("load_transform.transform_run_id is empty; keep the raw load run id if transforms ran inline")

    exports = _get(payload, ("exports",))
    if not isinstance(exports, dict):
        errors.append("exports must be an object")
    else:
        for table in REQUIRED_EXPORT_TABLES:
            if table not in exports:
                errors.append(f"exports.{table} is required")
                continue
            _require_text(payload, ("exports", table, "run_id"), errors)
            _require_gcs_uri(payload, ("exports", table, "gcs_uri"), errors)

    _require_text(payload, ("compatibility_audit", "run_id"), errors)
    _require_exact_text(payload, ("compatibility_audit", "artifact"), "compatibility-audit.json", errors)
    _require_bool(payload, ("compatibility_audit", "run_transform"), True, errors)
    _require_bool(payload, ("compatibility_audit", "fail_on_diff"), True, errors)

    exceptions = payload.get("exceptions", [])
    if exceptions is None:
        return EvidenceValidationResult(valid=not errors, errors=errors, warnings=warnings)
    if not isinstance(exceptions, list):
        errors.append("exceptions must be a list")
    elif exceptions:
        warnings.append("exceptions are present; verify each one has an owner and follow-up Issue URL")

    return EvidenceValidationResult(valid=not errors, errors=errors, warnings=warnings)


def _get(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = payload
    for part in path:
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _is_non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_text(payload: dict[str, Any], path: tuple[str, ...], errors: list[str]) -> None:
    value = _get(payload, path)
    if not _is_non_empty_text(value):
        errors.append(f"{'.'.join(path)} is required")


def _require_exact_text(payload: dict[str, Any], path: tuple[str, ...], expected: str, errors: list[str]) -> None:
    value = _get(payload, path)
    if value != expected:
        errors.append(f"{'.'.join(path)} must be {expected}")


def _require_gcs_uri(payload: dict[str, Any], path: tuple[str, ...], errors: list[str]) -> None:
    value = _get(payload, path)
    if not _is_non_empty_text(value) or not value.startswith("gs://"):
        errors.append(f"{'.'.join(path)} must be a gs:// URI")


def _require_bool(payload: dict[str, Any], path: tuple[str, ...], expected: bool, errors: list[str]) -> None:
    value = _get(payload, path)
    if value is not expected:
        errors.append(f"{'.'.join(path)} must be {expected}")
