from __future__ import annotations

from pathlib import Path

from elt_v2.brightdata import (
    BrightDataDatasetClient,
    BrightDataSerpClient,
    build_dataset_items_from_csv,
    build_serp_relevance_items_from_csv,
)


class FakeResponse:
    def __init__(self, payload, text="", status_code=200):
        self.payload = payload
        self.text = text or str(payload)
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self):
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if url.endswith("/trigger"):
            return FakeResponse({"snapshot_id": "snap-1"})
        return FakeResponse({"ok": True})

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if "/progress/" in url:
            return FakeResponse({"status": "ready"})
        return FakeResponse([{"review_id": "r1"}])


def test_builds_review_dataset_items_from_csv(tmp_path: Path):
    csv_file = tmp_path / "facilities.csv"
    csv_file.write_text(
        "facility_id,GoogleMap,web\n"
        "f1,https://maps.example/place/1,yes\n"
        "f2,https://maps.example/place/2,\n",
        encoding="utf-8",
    )

    items = build_dataset_items_from_csv(
        csv_path=csv_file,
        workflow_type="reviews_sequential",
        days_back=30,
        skip_column="web",
    )

    assert items == [{"url": "https://maps.example/place/1", "days_limit": 30}]


def test_builds_facility_search_items_from_address_csv(tmp_path: Path):
    csv_file = tmp_path / "addresses.csv"
    csv_file.write_text("住所\n東京都渋谷区\n", encoding="utf-8")

    items = build_dataset_items_from_csv(
        csv_path=csv_file,
        workflow_type="facility",
        query="歯科医院",
        skip_column="",
    )

    assert items == [
        {"url": "https://www.google.com/maps/search/%E6%9D%B1%E4%BA%AC%E9%83%BD%E6%B8%8B%E8%B0%B7%E5%8C%BA+%E6%AD%AF%E7%A7%91%E5%8C%BB%E9%99%A2/?hl=ja&gl=jp&brd_json=1"}
    ]


def test_build_items_respects_start_and_limit(tmp_path: Path):
    csv_file = tmp_path / "facilities.csv"
    csv_file.write_text(
        "GoogleMap,web\n"
        "https://maps.example/1,yes\n"
        "https://maps.example/2,yes\n"
        "https://maps.example/3,yes\n",
        encoding="utf-8",
    )

    items = build_dataset_items_from_csv(
        csv_path=csv_file,
        workflow_type="reviews_recent_relevance",
        start_row=2,
        row_limit=1,
    )

    assert items == [{"url": "https://maps.example/2", "days_limit": 10}]


def test_builds_serp_relevance_items_from_csv(tmp_path: Path):
    csv_file = tmp_path / "facilities.csv"
    csv_file.write_text(
        "facility_id,GoogleMap,web\n"
        "f1,https://maps.example/1,yes\n"
        "f2,https://maps.example/2,\n"
        "f3,https://maps.example/3,yes\n",
        encoding="utf-8",
    )

    items = build_serp_relevance_items_from_csv(
        csv_path=csv_file,
        skip_column="web",
        start_row=1,
        row_limit=3,
    )

    assert items == [
        {"index": 1, "url": "https://maps.example/1", "facility_id": "f1"},
        {"index": 3, "url": "https://maps.example/3", "facility_id": "f3"},
    ]


def test_dataset_client_runs_trigger_progress_snapshot():
    session = FakeSession()
    client = BrightDataDatasetClient("token", session=session)

    result = client.run_snapshot(
        dataset_id="dataset-1",
        items=[{"url": "https://maps.example/1"}],
        max_wait_minutes=1,
        poll_interval_seconds=0,
    )

    assert result.snapshot_id == "snap-1"
    assert result.data == [{"review_id": "r1"}]
    assert session.posts[0][0] == "https://api.brightdata.com/datasets/v3/trigger"
    assert session.posts[0][1]["params"] == {"dataset_id": "dataset-1", "format": "json"}


def test_serp_client_posts_request_payload():
    session = FakeSession()
    client = BrightDataSerpClient("token", session=session)

    result = client.request(zone_name="serp_api2", url="https://www.google.com/search?q=test")

    assert result == {"ok": True}
    assert session.posts[0][0] == "https://api.brightdata.com/request"
    assert session.posts[0][1]["json"] == {
        "zone": "serp_api2",
        "url": "https://www.google.com/search?q=test",
        "format": "json",
    }
