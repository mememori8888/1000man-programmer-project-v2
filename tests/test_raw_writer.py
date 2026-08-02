from __future__ import annotations

from datetime import datetime, timezone

import pytest

from elt_v2.raw_writer import build_raw_object, write_raw_object_local


def test_builds_deterministic_json_raw_object(tmp_path):
    input_path = tmp_path / "reviews.json"
    input_path.write_text('{"reviews": [{"review_id": "r1"}]}\n', encoding="utf-8")

    raw_object = build_raw_object(
        input_path=input_path,
        source_run_id="gh-run-123",
        dataset_kind="reviews",
        extracted_at=datetime(2026, 8, 3, 1, 2, 3, tzinfo=timezone.utc),
    )

    assert raw_object.object_name.startswith("raw/reviews/2026/08/03/source_run_id=gh-run-123/")
    assert raw_object.object_name.endswith(".json")
    assert raw_object.content_type == "application/json"
    assert raw_object.manifest["source_run_id"] == "gh-run-123"
    assert raw_object.manifest["byte_size"] == input_path.stat().st_size


def test_writes_local_payload_and_manifest(tmp_path):
    input_path = tmp_path / "facilities.csv"
    input_path.write_text("facility_id,name\nf1,Clinic\n", encoding="utf-8")

    raw_object = build_raw_object(
        input_path=input_path,
        source_run_id="run/with spaces",
        dataset_kind="facilities",
        extracted_at=datetime(2026, 8, 3, 1, 2, 3, tzinfo=timezone.utc),
    )
    destination = write_raw_object_local(raw_object, tmp_path / "out")

    assert destination.exists()
    assert destination.read_bytes() == input_path.read_bytes()
    assert destination.with_suffix(destination.suffix + ".manifest.json").exists()
    assert "source_run_id=run-with-spaces" in raw_object.object_name


def test_rejects_invalid_dataset_kind(tmp_path):
    input_path = tmp_path / "reviews.json"
    input_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="dataset_kind"):
        build_raw_object(
            input_path=input_path,
            source_run_id="run-1",
            dataset_kind="unknown",
        )


def test_rejects_empty_csv_header(tmp_path):
    input_path = tmp_path / "empty.csv"
    input_path.write_text("\n", encoding="utf-8")

    with pytest.raises(ValueError, match="header"):
        build_raw_object(
            input_path=input_path,
            source_run_id="run-1",
            dataset_kind="reviews",
        )


def test_builds_serp_relevance_raw_object(tmp_path):
    input_path = tmp_path / "serp.json"
    input_path.write_text('{"request":{"url":"https://example.com"},"response":{"ok":true}}', encoding="utf-8")

    raw_object = build_raw_object(
        input_path=input_path,
        source_run_id="serp-run",
        dataset_kind="serp_relevance",
        extracted_at=datetime(2026, 8, 3, 1, 2, 3, tzinfo=timezone.utc),
    )

    assert raw_object.manifest["dataset_kind"] == "serp_relevance"
    assert raw_object.object_name.startswith("raw/serp_relevance/2026/08/03/source_run_id=serp-run/")
