from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_DATASET_KINDS = {"reviews", "facilities"}
TRANSFORM_SQL_FILES = [
    "sql/bigquery/001_create_raw_tables.sql",
    "sql/bigquery/002_create_mart_tables.sql",
    "sql/bigquery/010_parse_raw_reviews.sql",
    "sql/bigquery/011_parse_raw_facilities.sql",
    "sql/bigquery/101_deduplicate_reviews.sql",
]


@dataclass(frozen=True)
class RawLoadPlan:
    project_id: str
    dataset: str
    table: str
    source_uri: str
    source_run_id: str
    dataset_kind: str
    raw_object_uri: str
    payload_sha256: str
    extracted_at: str

    @property
    def table_id(self) -> str:
        return f"{self.project_id}.{self.dataset}.{self.table}"


def build_raw_table_row(*, plan: RawLoadPlan, raw_payload: str) -> dict[str, Any]:
    return {
        "source_run_id": plan.source_run_id,
        "raw_object_uri": plan.raw_object_uri,
        "raw_payload": raw_payload,
        "source_system": "brightdata",
        "extracted_at": plan.extracted_at,
        "payload_sha256": plan.payload_sha256,
        "dataset_kind": plan.dataset_kind,
    }


def build_raw_load_plan(
    *,
    manifest: dict[str, Any],
    project_id: str,
    dataset: str,
    source_uri: str | None = None,
) -> RawLoadPlan:
    dataset_kind = str(manifest.get("dataset_kind", "")).strip()
    if dataset_kind not in VALID_DATASET_KINDS:
        raise ValueError(f"dataset_kind must be one of: {', '.join(sorted(VALID_DATASET_KINDS))}")

    _validate_identifier(project_id, "project_id", allow_dash=True)
    _validate_identifier(dataset, "dataset")

    table = "raw_reviews" if dataset_kind == "reviews" else "raw_facilities"
    raw_object_uri = source_uri or str(manifest.get("gcs_uri") or manifest.get("raw_object_uri") or "")
    if not raw_object_uri:
        object_name = str(manifest.get("object_name", "")).strip()
        bucket = str(manifest.get("bucket", "")).strip()
        if object_name and bucket:
            raw_object_uri = f"gs://{bucket}/{object_name}"

    if not raw_object_uri:
        raise ValueError("manifest must include gcs_uri, raw_object_uri, or bucket + object_name")
    if not raw_object_uri.startswith("gs://"):
        raise ValueError("raw_object_uri must be a gs:// URI for BigQuery load")

    return RawLoadPlan(
        project_id=project_id,
        dataset=dataset,
        table=table,
        source_uri=raw_object_uri,
        source_run_id=str(manifest["source_run_id"]),
        dataset_kind=dataset_kind,
        raw_object_uri=raw_object_uri,
        payload_sha256=str(manifest.get("sha256", "")),
        extracted_at=str(manifest["extracted_at"]),
    )


def render_sql_template(sql_text: str, *, project_id: str, dataset: str) -> str:
    _validate_identifier(project_id, "project_id", allow_dash=True)
    _validate_identifier(dataset, "dataset")
    return sql_text.replace("${PROJECT_ID}", project_id).replace("${DATASET}", dataset)


def load_manifest_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_raw_payload_to_bigquery(plan: RawLoadPlan, *, payload_file: Path) -> str:
    try:
        from google.cloud import bigquery
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-bigquery is required. Install with: pip install .[gcp]"
        ) from exc

    client = bigquery.Client(project=plan.project_id)
    row = build_raw_table_row(
        plan=plan,
        raw_payload=payload_file.read_text(encoding="utf-8-sig"),
    )
    errors = client.insert_rows_json(plan.table_id, [row])
    if errors:
        raise RuntimeError(f"BigQuery insert failed: {errors}")
    return "insert_rows_json"


def run_sql_file(path: Path, *, project_id: str, dataset: str) -> str:
    try:
        from google.cloud import bigquery
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-bigquery is required. Install with: pip install .[gcp]"
        ) from exc

    sql = render_sql_template(path.read_text(encoding="utf-8"), project_id=project_id, dataset=dataset)
    client = bigquery.Client(project=project_id)
    query_job = client.query(sql)
    query_job.result()
    return query_job.job_id


def _validate_identifier(value: str, name: str, *, allow_dash: bool = False) -> None:
    pattern = r"^[A-Za-z_][A-Za-z0-9_]*$"
    if allow_dash:
        pattern = r"^[A-Za-z_][A-Za-z0-9_-]*$"
    if not re.match(pattern, value):
        raise ValueError(f"{name} is not a valid BigQuery identifier: {value}")
