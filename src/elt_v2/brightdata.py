from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote_plus

import requests


REVIEW_URL_COLUMNS = ["GoogleMap", "google_map_url", "google_map", "web", "url"]
FACILITY_ADDRESS_COLUMNS = ["address", "住所", "prefecture", "都道府県"]


class HTTPSession(Protocol):
    def post(self, url: str, **kwargs: Any) -> Any: ...

    def get(self, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class DatasetSnapshotResult:
    snapshot_id: str
    data: Any


@dataclass(frozen=True)
class DatasetCsvValidation:
    csv_path: str
    workflow_type: str
    total_rows: int
    selected_rows: int
    item_count: int
    required_any_columns: tuple[str, ...]
    present_columns: tuple[str, ...]
    skip_column: str


class BrightDataDatasetClient:
    def __init__(self, api_token: str, session: HTTPSession | None = None) -> None:
        if not api_token:
            raise ValueError("api_token is required")
        self.api_token = api_token
        self.session = session or requests.Session()
        self.base_url = "https://api.brightdata.com/datasets/v3"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def trigger(self, *, dataset_id: str, items: list[dict[str, Any]]) -> str:
        if not dataset_id:
            raise ValueError("dataset_id is required")
        if not items:
            raise ValueError("items must not be empty")

        response = self.session.post(
            f"{self.base_url}/trigger",
            params={"dataset_id": dataset_id, "format": "json"},
            headers=self.headers,
            json=items,
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        snapshot_id = payload.get("snapshot_id")
        if not snapshot_id:
            raise RuntimeError(f"BrightData trigger response did not include snapshot_id: {payload}")
        return str(snapshot_id)

    def wait(self, *, snapshot_id: str, max_wait_seconds: int, poll_interval_seconds: int = 15) -> None:
        deadline = time.monotonic() + max_wait_seconds
        last_status = ""
        while time.monotonic() < deadline:
            response = self.session.get(
                f"{self.base_url}/progress/{snapshot_id}",
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            last_status = str(payload.get("status") or "")
            if last_status.lower() in {"ready", "done", "completed", "success"}:
                return
            if last_status.lower() in {"failed", "error", "cancelled"}:
                raise RuntimeError(f"BrightData snapshot failed: {payload}")
            time.sleep(poll_interval_seconds)
        raise TimeoutError(f"Timed out waiting for snapshot {snapshot_id}; last_status={last_status}")

    def download(self, *, snapshot_id: str) -> Any:
        response = self.session.get(
            f"{self.base_url}/snapshot/{snapshot_id}?format=json",
            headers={"Authorization": f"Bearer {self.api_token}"},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()

    def run_snapshot(
        self,
        *,
        dataset_id: str,
        items: list[dict[str, Any]],
        max_wait_minutes: int,
        poll_interval_seconds: int = 15,
    ) -> DatasetSnapshotResult:
        snapshot_id = self.trigger(dataset_id=dataset_id, items=items)
        self.wait(
            snapshot_id=snapshot_id,
            max_wait_seconds=max_wait_minutes * 60,
            poll_interval_seconds=poll_interval_seconds,
        )
        return DatasetSnapshotResult(snapshot_id=snapshot_id, data=self.download(snapshot_id=snapshot_id))


class BrightDataSerpClient:
    def __init__(self, api_token: str, session: HTTPSession | None = None) -> None:
        if not api_token:
            raise ValueError("api_token is required")
        self.api_token = api_token
        self.session = session or requests.Session()
        self.endpoint = "https://api.brightdata.com/request"

    def request(self, *, zone_name: str, url: str, response_format: str = "json") -> Any:
        response = self.session.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            json={"zone": zone_name, "url": url, "format": response_format},
            timeout=120,
        )
        response.raise_for_status()
        if response_format == "raw":
            return response.text
        return response.json()


def build_dataset_items_from_csv(
    *,
    csv_path: Path,
    workflow_type: str,
    days_back: int = 10,
    skip_column: str = "web",
    start_row: int = 1,
    row_limit: int | None = None,
    query: str = "",
) -> list[dict[str, Any]]:
    rows = _read_csv_rows(csv_path)
    selected = rows[start_row - 1 :]
    if row_limit is not None:
        selected = selected[:row_limit]

    items: list[dict[str, Any]] = []
    for row in selected:
        if skip_column and not str(row.get(skip_column, "")).strip():
            continue

        if workflow_type in {"reviews", "reviews_sequential", "reviews_recent_relevance"}:
            url = _first_present(row, ["GoogleMap", "google_map_url", "google_map", "web", "url"])
            if url:
                items.append({"url": url, "days_limit": days_back})
            continue

        if workflow_type == "facility":
            address = _first_present(row, ["address", "住所", "prefecture", "都道府県"])
            search_query = " ".join(part for part in [address, query] if part).strip()
            if search_query:
                items.append(
                    {
                        "url": f"https://www.google.com/maps/search/{quote_plus(search_query)}/?hl=ja&gl=jp&brd_json=1"
                    }
                )
            continue

        raise ValueError(f"unsupported workflow_type: {workflow_type}")

    return items


def validate_dataset_csv(
    *,
    csv_path: Path,
    workflow_type: str,
    days_back: int = 10,
    skip_column: str = "web",
    start_row: int = 1,
    row_limit: int | None = None,
    query: str = "",
) -> DatasetCsvValidation:
    if start_row < 1:
        raise ValueError("start_row must be greater than 0")
    if row_limit is not None and row_limit < 1:
        raise ValueError("row_limit must be greater than 0 when provided")
    if not csv_path.exists():
        raise ValueError(f"csv_path does not exist: {csv_path}")
    if csv_path.suffix.lower() != ".csv":
        raise ValueError("csv_path must be a .csv file")

    header, rows = _read_csv_header_and_rows(csv_path)
    if not header:
        raise ValueError(f"csv_path has no header row: {csv_path}")

    if workflow_type in {"reviews", "reviews_sequential", "reviews_recent_relevance"}:
        required_any_columns = tuple(REVIEW_URL_COLUMNS)
        if skip_column and not _has_any_column(header, [skip_column]):
            raise ValueError(f"skip_column is not present in CSV header: {skip_column}")
    elif workflow_type == "facility":
        required_any_columns = tuple(FACILITY_ADDRESS_COLUMNS)
    else:
        raise ValueError(f"unsupported workflow_type: {workflow_type}")

    if not _has_any_column(header, list(required_any_columns)):
        raise ValueError(
            "CSV must include at least one of these columns for "
            f"{workflow_type}: {', '.join(required_any_columns)}"
        )

    selected_rows = rows[start_row - 1 :]
    if row_limit is not None:
        selected_rows = selected_rows[:row_limit]
    if not selected_rows:
        raise ValueError("selected CSV range has no rows")

    item_count = len(
        build_dataset_items_from_csv(
            csv_path=csv_path,
            workflow_type=workflow_type,
            days_back=days_back,
            skip_column=skip_column,
            start_row=start_row,
            row_limit=row_limit,
            query=query,
        )
    )
    if item_count < 1:
        raise ValueError("selected CSV range produced no BrightData input items")

    present_columns = tuple(column for column in required_any_columns if _has_any_column(header, [column]))
    return DatasetCsvValidation(
        csv_path=str(csv_path),
        workflow_type=workflow_type,
        total_rows=len(rows),
        selected_rows=len(selected_rows),
        item_count=item_count,
        required_any_columns=required_any_columns,
        present_columns=present_columns,
        skip_column=skip_column,
    )


def build_serp_relevance_items_from_csv(
    *,
    csv_path: Path,
    skip_column: str = "web",
    start_row: int = 1,
    row_limit: int | None = None,
) -> list[dict[str, Any]]:
    rows = _read_csv_rows(csv_path)
    selected = rows[start_row - 1 :]
    if row_limit is not None:
        selected = selected[:row_limit]

    items: list[dict[str, Any]] = []
    for index, row in enumerate(selected, start=start_row):
        if skip_column and not str(row.get(skip_column, "")).strip():
            continue

        url = _first_present(row, ["GoogleMap", "google_map_url", "google_map", "web", "url"])
        if not url:
            continue

        facility_id = _first_present(row, ["facility_id", "place_id", "fid", "gid", "id"])
        items.append(
            {
                "index": index,
                "url": url,
                "facility_id": facility_id or url,
            }
        )

    return items


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    return _read_csv_header_and_rows(csv_path)[1]


def _read_csv_header_and_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _first_present(row: dict[str, str], keys: list[str]) -> str:
    lowered = {key.lower(): value for key, value in row.items()}
    for key in keys:
        value = row.get(key)
        if value:
            return str(value).strip()
        value = lowered.get(key.lower())
        if value:
            return str(value).strip()
    return ""


def _has_any_column(header: list[str], keys: list[str]) -> bool:
    lowered = {column.lower() for column in header}
    return any(key in header or key.lower() in lowered for key in keys)
