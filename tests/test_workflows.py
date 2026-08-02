from __future__ import annotations

from pathlib import Path


def test_brightdata_extract_does_not_emit_raw_payload_as_job_output():
    workflow_text = Path(".github/workflows/brightdata-extract.yml").read_text(encoding="utf-8")

    assert "payload_json:" not in workflow_text
    assert "payload_json<<EOF" not in workflow_text
    assert "raw-ingest:" not in workflow_text
    assert "work/brightdata-result.json" in workflow_text
    assert "elt-raw-write" in workflow_text
