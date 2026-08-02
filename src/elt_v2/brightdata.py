from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote_plus

import requests


class HTTPSession(Protocol):
    def post(self, url: str, **kwargs: Any) -> Any: ...

    def get(self, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class DatasetSnapshotResult:
    snapshot_id: str
    data: Any


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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


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
