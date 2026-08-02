from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote


VALID_DATASET_KINDS = {"reviews", "facilities", "serp_relevance"}
RAW_TABLE_BY_DATASET_KIND = {
    "reviews": "raw_reviews",
    "facilities": "raw_facilities",
    "serp_relevance": "raw_serp_responses",
}
TRANSFORM_SQL_FILES = [
    "sql/bigquery/001_create_raw_tables.sql",
    "sql/bigquery/002_create_mart_tables.sql",
    "sql/bigquery/010_parse_raw_reviews.sql",
    "sql/bigquery/011_parse_raw_facilities.sql",
    "sql/bigquery/020_parse_raw_serp_responses.sql",
    "sql/bigquery/101_deduplicate_reviews.sql",
    "sql/bigquery/120_build_review_relevance_ranks.sql",
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


@dataclass(frozen=True)
class CsvExportPlan:
    project_id: str
    dataset: str
    table: str
    destination_uri: str

    @property
    def table_id(self) -> str:
        return f"{self.project_id}.{self.dataset}.{self.table}"


@dataclass(frozen=True)
class CompatibilityAuditPlan:
    project_id: str
    dataset: str
    legacy_csv_path: Path
    bq_table: str
    legacy_key_columns: tuple[str, ...]
    bq_key_columns: tuple[str, ...]
    temp_table: str
    sample_limit: int = 20

    @property
    def temp_table_id(self) -> str:
        return f"{self.project_id}.{self.dataset}.{self.temp_table}"

    @property
    def bq_table_id(self) -> str:
        return f"{self.project_id}.{self.dataset}.{self.bq_table}"


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

    table = RAW_TABLE_BY_DATASET_KIND[dataset_kind]
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


def build_csv_export_plan(
    *,
    project_id: str,
    dataset: str,
    table: str,
    destination_uri: str = "",
    gcs_bucket: str = "",
    legacy_output_path: str = "",
) -> CsvExportPlan:
    _validate_identifier(project_id, "project_id", allow_dash=True)
    _validate_identifier(dataset, "dataset")
    _validate_identifier(table, "table")
    destination_uri = resolve_csv_export_destination_uri(
        destination_uri=destination_uri,
        gcs_bucket=gcs_bucket,
        legacy_output_path=legacy_output_path,
        table=table,
    )
    if not destination_uri.startswith("gs://"):
        raise ValueError("destination_uri must be a gs:// URI")
    if not destination_uri.lower().endswith(".csv"):
        raise ValueError("destination_uri must end with .csv, including sharded exports such as file-*.csv")
    return CsvExportPlan(
        project_id=project_id,
        dataset=dataset,
        table=table,
        destination_uri=destination_uri,
    )


def resolve_csv_export_destination_uri(
    *,
    destination_uri: str = "",
    gcs_bucket: str = "",
    legacy_output_path: str = "",
    table: str = "",
) -> str:
    destination_uri = destination_uri.strip()
    if destination_uri:
        return destination_uri

    bucket = gcs_bucket.strip()
    if not bucket:
        raise ValueError("destination_uri or gcs_bucket is required")

    normalized = (legacy_output_path.strip() or f"{table}.csv").replace("\\", "/").lstrip("/")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"legacy_output_path is not safe: {legacy_output_path}")

    path = PurePosixPath("exports", *parts)
    if path.suffix.lower() != ".csv":
        path = path.with_suffix(".csv")
    if "*" not in path.name:
        path = path.with_name(f"{path.stem}-*{path.suffix}")
    return f"gs://{bucket}/{path.as_posix()}"


def build_compatibility_audit_plan(
    *,
    project_id: str,
    dataset: str,
    legacy_csv_path: Path,
    bq_table: str,
    legacy_key_columns: list[str],
    bq_key_columns: list[str] | None = None,
    temp_table: str = "_compat_legacy_csv_audit",
    sample_limit: int = 20,
) -> CompatibilityAuditPlan:
    _validate_identifier(project_id, "project_id", allow_dash=True)
    _validate_identifier(dataset, "dataset")
    _validate_identifier(bq_table, "bq_table")
    _validate_identifier(temp_table, "temp_table")
    if not legacy_csv_path.exists():
        raise ValueError(f"legacy_csv_path does not exist: {legacy_csv_path}")
    if legacy_csv_path.suffix.lower() != ".csv":
        raise ValueError("legacy_csv_path must be a .csv file")
    if not legacy_key_columns:
        raise ValueError("at least one legacy_key_column is required")
    resolved_bq_key_columns = bq_key_columns or legacy_key_columns
    if len(legacy_key_columns) != len(resolved_bq_key_columns):
        raise ValueError("legacy_key_columns and bq_key_columns must have the same length")
    if sample_limit < 1:
        raise ValueError("sample_limit must be greater than 0")

    for column in [*legacy_key_columns, *resolved_bq_key_columns]:
        _validate_identifier(column, "key_column")

    return CompatibilityAuditPlan(
        project_id=project_id,
        dataset=dataset,
        legacy_csv_path=legacy_csv_path,
        bq_table=bq_table,
        legacy_key_columns=tuple(legacy_key_columns),
        bq_key_columns=tuple(resolved_bq_key_columns),
        temp_table=temp_table,
        sample_limit=sample_limit,
    )


def render_sql_template(sql_text: str, *, project_id: str, dataset: str) -> str:
    _validate_identifier(project_id, "project_id", allow_dash=True)
    _validate_identifier(dataset, "dataset")
    return sql_text.replace("${PROJECT_ID}", project_id).replace("${DATASET}", dataset)


def render_compatibility_audit_sql(plan: CompatibilityAuditPlan) -> str:
    legacy_key = _key_expression("legacy", plan.legacy_key_columns)
    bq_key = _key_expression("mart", plan.bq_key_columns)
    return f"""
with
legacy as (
  select
    {legacy_key} as compat_key
  from `{plan.temp_table_id}` as legacy
),
mart as (
  select
    {bq_key} as compat_key
  from `{plan.bq_table_id}` as mart
),
legacy_counts as (
  select count(*) as row_count, count(distinct compat_key) as distinct_key_count
  from legacy
),
mart_counts as (
  select count(*) as row_count, count(distinct compat_key) as distinct_key_count
  from mart
),
missing_in_mart as (
  select compat_key from legacy
  except distinct
  select compat_key from mart
),
missing_in_legacy as (
  select compat_key from mart
  except distinct
  select compat_key from legacy
)
select
  (select row_count from legacy_counts) as legacy_row_count,
  (select row_count from mart_counts) as bq_row_count,
  (select distinct_key_count from legacy_counts) as legacy_distinct_key_count,
  (select distinct_key_count from mart_counts) as bq_distinct_key_count,
  (select count(*) from missing_in_mart) as missing_in_bq_count,
  (select count(*) from missing_in_legacy) as missing_in_legacy_count,
  array(
    select compat_key from missing_in_mart
    order by compat_key
    limit {plan.sample_limit}
  ) as missing_in_bq_sample,
  array(
    select compat_key from missing_in_legacy
    order by compat_key
    limit {plan.sample_limit}
  ) as missing_in_legacy_sample
""".strip()


def compatibility_audit_has_diff(result: dict[str, Any]) -> bool:
    return int(result["missing_in_bq_count"]) > 0 or int(result["missing_in_legacy_count"]) > 0


def build_recent_review_serp_targets_sql(
    *,
    project_id: str,
    dataset: str,
    days_back: int,
    row_limit: int | None = None,
) -> str:
    _validate_identifier(project_id, "project_id", allow_dash=True)
    _validate_identifier(dataset, "dataset")
    if days_back < 1:
        raise ValueError("days_back must be greater than 0")
    if row_limit is not None and row_limit < 1:
        raise ValueError("row_limit must be greater than 0 when provided")

    limit_clause = f"\nlimit {row_limit}" if row_limit is not None else ""
    return f"""
with recent_facilities as (
  select
    facility_id,
    max(extracted_at) as latest_review_extracted_at,
    count(*) as recent_review_count
  from `{project_id}.{dataset}.fact_reviews`
  where coalesce(review_date, date(extracted_at)) >= date_sub(current_date(), interval {days_back} day)
  group by facility_id
),
review_input_urls as (
  select
    facility_id,
    array_agg(
      coalesce(
        nullif(json_value(raw_review_json, '$.input.url'), ''),
        nullif(json_value(raw_review_json, '$.url'), '')
      ) ignore nulls
      order by extracted_at desc
      limit 1
    )[safe_offset(0)] as google_map_url
  from `{project_id}.{dataset}.raw_reviews_parsed`
  group by facility_id
),
target_candidates as (
  select
    recent_facilities.facility_id,
    coalesce(
      nullif(dim_facilities.google_map_url, ''),
      nullif(review_input_urls.google_map_url, ''),
      if(starts_with(recent_facilities.facility_id, 'http'), recent_facilities.facility_id, null)
    ) as url,
    recent_facilities.latest_review_extracted_at,
    recent_facilities.recent_review_count
  from recent_facilities
  left join `{project_id}.{dataset}.dim_facilities` as dim_facilities
    using (facility_id)
  left join review_input_urls
    using (facility_id)
),
targets as (
  select *
  from target_candidates
  where url is not null
    and url != ''
)
select
  row_number() over (
    order by latest_review_extracted_at desc, recent_review_count desc, facility_id
  ) as index,
  facility_id,
  url
from targets{limit_clause}
""".strip()


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


def parse_gcs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError("GCS URI must start with gs://")
    remainder = uri[len("gs://") :]
    bucket, separator, object_name = remainder.partition("/")
    if not bucket or not separator or not object_name:
        raise ValueError("GCS URI must include bucket and object name")
    return bucket, unquote(object_name)


def download_gcs_text(uri: str) -> str:
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-storage is required for GCS replay. Install with: pip install .[gcp]"
        ) from exc

    bucket_name, object_name = parse_gcs_uri(uri)
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(object_name)
    return blob.download_as_text(encoding="utf-8")


def replay_gcs_raw_object_to_bigquery(
    *,
    raw_uri: str,
    manifest_uri: str | None,
    project_id: str,
    dataset: str,
) -> dict[str, str]:
    resolved_manifest_uri = manifest_uri or f"{raw_uri}.manifest.json"
    manifest = json.loads(download_gcs_text(resolved_manifest_uri))
    raw_payload = download_gcs_text(raw_uri)
    plan = build_raw_load_plan(
        manifest=manifest,
        project_id=project_id,
        dataset=dataset,
        source_uri=raw_uri,
    )

    try:
        from google.cloud import bigquery
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-bigquery is required. Install with: pip install .[gcp]"
        ) from exc

    client = bigquery.Client(project=plan.project_id)
    errors = client.insert_rows_json(
        plan.table_id,
        [build_raw_table_row(plan=plan, raw_payload=raw_payload)],
    )
    if errors:
        raise RuntimeError(f"BigQuery insert failed: {errors}")
    return {
        "job_id": "insert_rows_json",
        "table_id": plan.table_id,
        "raw_uri": raw_uri,
        "manifest_uri": resolved_manifest_uri,
    }


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


def run_sql_files(paths: list[Path], *, project_id: str, dataset: str) -> list[dict[str, str]]:
    results = []
    for path in paths:
        job_id = run_sql_file(path, project_id=project_id, dataset=dataset)
        results.append({"sql_file": str(path), "job_id": job_id})
    return results


def export_table_to_gcs_csv(plan: CsvExportPlan) -> str:
    try:
        from google.cloud import bigquery
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-bigquery is required. Install with: pip install .[gcp]"
        ) from exc

    client = bigquery.Client(project=plan.project_id)
    job_config = bigquery.ExtractJobConfig(
        destination_format=bigquery.DestinationFormat.CSV,
        print_header=True,
    )
    extract_job = client.extract_table(
        plan.table_id,
        plan.destination_uri,
        job_config=job_config,
    )
    extract_job.result()
    return extract_job.job_id


def run_compatibility_audit(plan: CompatibilityAuditPlan) -> dict[str, Any]:
    try:
        from google.cloud import bigquery
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-bigquery is required. Install with: pip install .[gcp]"
        ) from exc

    client = bigquery.Client(project=plan.project_id)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    with plan.legacy_csv_path.open("rb") as csv_file:
        load_job = client.load_table_from_file(csv_file, plan.temp_table_id, job_config=job_config)
    load_job.result()

    rows = list(client.query(render_compatibility_audit_sql(plan)).result())
    if len(rows) != 1:
        raise RuntimeError(f"compatibility audit expected one summary row, got {len(rows)}")

    row = rows[0]
    return {
        "legacy_csv": str(plan.legacy_csv_path),
        "legacy_temp_table": plan.temp_table_id,
        "bq_table": plan.bq_table_id,
        "legacy_key_columns": list(plan.legacy_key_columns),
        "bq_key_columns": list(plan.bq_key_columns),
        "legacy_row_count": int(row["legacy_row_count"]),
        "bq_row_count": int(row["bq_row_count"]),
        "legacy_distinct_key_count": int(row["legacy_distinct_key_count"]),
        "bq_distinct_key_count": int(row["bq_distinct_key_count"]),
        "missing_in_bq_count": int(row["missing_in_bq_count"]),
        "missing_in_legacy_count": int(row["missing_in_legacy_count"]),
        "missing_in_bq_sample": list(row["missing_in_bq_sample"]),
        "missing_in_legacy_sample": list(row["missing_in_legacy_sample"]),
    }


def query_recent_review_serp_targets(
    *,
    project_id: str,
    dataset: str,
    days_back: int,
    row_limit: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    try:
        from google.cloud import bigquery
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-bigquery is required. Install with: pip install .[gcp]"
        ) from exc

    sql = build_recent_review_serp_targets_sql(
        project_id=project_id,
        dataset=dataset,
        days_back=days_back,
        row_limit=row_limit,
    )
    client = bigquery.Client(project=project_id)
    rows = client.query(sql).result()
    return {
        "include": [
            {
                "index": int(row["index"]),
                "facility_id": str(row["facility_id"]),
                "url": str(row["url"]),
            }
            for row in rows
        ]
    }


def _validate_identifier(value: str, name: str, *, allow_dash: bool = False) -> None:
    pattern = r"^[A-Za-z_][A-Za-z0-9_]*$"
    if allow_dash:
        pattern = r"^[A-Za-z_][A-Za-z0-9_-]*$"
    if not re.match(pattern, value):
        raise ValueError(f"{name} is not a valid BigQuery identifier: {value}")


def _key_expression(alias: str, columns: tuple[str, ...]) -> str:
    if len(columns) == 1:
        return f"cast({alias}.{columns[0]} as string)"
    fields = ", ".join(f"{alias}.{column} as {column}" for column in columns)
    return f"to_json_string(struct({fields}))"
