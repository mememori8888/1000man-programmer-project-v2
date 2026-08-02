from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPPORTED_KINDS = {"reviews", "facilities", "serp_relevance"}


@dataclass(frozen=True)
class RawObject:
    """A deterministic raw object ready for local storage or GCS upload."""

    object_name: str
    content_type: str
    payload_bytes: bytes
    manifest: dict[str, Any]


def build_raw_object(
    *,
    input_path: Path,
    source_run_id: str,
    dataset_kind: str,
    extracted_at: datetime | None = None,
) -> RawObject:
    if dataset_kind not in SUPPORTED_KINDS:
        raise ValueError(f"dataset_kind must be one of: {', '.join(sorted(SUPPORTED_KINDS))}")

    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if not input_path.is_file():
        raise ValueError(f"input_path must be a file: {input_path}")

    extracted_at = extracted_at or datetime.now(timezone.utc)
    payload_bytes = input_path.read_bytes()
    digest = hashlib.sha256(payload_bytes).hexdigest()
    suffix = input_path.suffix.lower()
    content_type = mimetypes.guess_type(input_path.name)[0] or "application/octet-stream"

    if suffix == ".json":
        _validate_json_payload(payload_bytes)
        normalized_suffix = "json"
        content_type = "application/json"
    elif suffix == ".csv":
        _validate_csv_payload(payload_bytes)
        normalized_suffix = "csv"
        content_type = "text/csv"
    else:
        raise ValueError("raw input must be .json or .csv")

    date_prefix = extracted_at.strftime("%Y/%m/%d")
    timestamp = extracted_at.strftime("%Y%m%dT%H%M%SZ")
    object_name = (
        f"raw/{dataset_kind}/{date_prefix}/"
        f"source_run_id={_safe_segment(source_run_id)}/"
        f"{timestamp}_{digest[:12]}.{normalized_suffix}"
    )

    manifest = {
        "source_run_id": source_run_id,
        "dataset_kind": dataset_kind,
        "object_name": object_name,
        "content_type": content_type,
        "sha256": digest,
        "byte_size": len(payload_bytes),
        "extracted_at": extracted_at.isoformat().replace("+00:00", "Z"),
        "source_file": str(input_path),
    }

    return RawObject(
        object_name=object_name,
        content_type=content_type,
        payload_bytes=payload_bytes,
        manifest=manifest,
    )


def write_raw_object_local(raw_object: RawObject, output_root: Path) -> Path:
    destination = output_root / raw_object.object_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw_object.payload_bytes)

    manifest_path = destination.with_suffix(destination.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(raw_object.manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def upload_raw_object_to_gcs(raw_object: RawObject, bucket_name: str) -> str:
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-storage is required for GCS uploads. "
            "Install with: pip install .[gcp]"
        ) from exc

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(raw_object.object_name)
    blob.upload_from_string(raw_object.payload_bytes, content_type=raw_object.content_type)

    manifest_blob = bucket.blob(raw_object.object_name + ".manifest.json")
    manifest_blob.upload_from_string(
        json.dumps(raw_object.manifest, ensure_ascii=False, indent=2) + "\n",
        content_type="application/json",
    )
    return f"gs://{bucket_name}/{raw_object.object_name}"


def manifest_as_dict(raw_object: RawObject) -> dict[str, Any]:
    return asdict(raw_object)["manifest"]


def _validate_json_payload(payload_bytes: bytes) -> None:
    try:
        json.loads(payload_bytes.decode("utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 - include JSON parser detail in CLI errors.
        raise ValueError(f"invalid JSON payload: {exc}") from exc


def _validate_csv_payload(payload_bytes: bytes) -> None:
    try:
        text = payload_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV payload must be UTF-8 or UTF-8 with BOM") from exc

    reader = csv.reader(text.splitlines())
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV payload must include a header row") from exc

    if not any(cell.strip() for cell in header):
        raise ValueError("CSV header row must contain at least one column")


def _safe_segment(value: str) -> str:
    safe = []
    for char in value.strip():
        if char.isalnum() or char in {"-", "_", "."}:
            safe.append(char)
        else:
            safe.append("-")
    result = "".join(safe).strip("-._")
    if not result:
        raise ValueError("source_run_id must contain at least one safe character")
    return result[:120]
