from __future__ import annotations

import json

from elt_v2.evidence import build_evidence_template, validate_evidence
from elt_v2.evidence_cli import main


def complete_evidence_payload():
    payload = build_evidence_template()
    payload["preflight"]["run_id"] = "1001"
    payload["preflight"]["summary_url"] = "https://github.com/mememori8888/1000man-programmer-project-v2/actions/runs/1001"
    payload["issueops"]["issue_url"] = "https://github.com/mememori8888/1000man-programmer-project-v2/issues/1"
    payload["extract"]["run_id"] = "1002"
    payload["extract"]["raw_payload_gcs_uri"] = "gs://raw-bucket/raw/reviews/payload.json"
    payload["extract"]["raw_manifest_gcs_uri"] = "gs://raw-bucket/raw/reviews/payload.json.manifest.json"
    payload["load_transform"]["run_id"] = "1002"
    payload["load_transform"]["raw_load_job_id"] = "insert_rows_json"
    payload["load_transform"]["transform_run_id"] = "1002"
    for table in payload["exports"]:
        payload["exports"][table]["run_id"] = "1004"
        payload["exports"][table]["gcs_uri"] = f"gs://export-bucket/exports/{table}-*.csv"
    payload["compatibility_audit"]["run_id"] = "1003"
    return payload


def test_validates_complete_release_evidence():
    result = validate_evidence(complete_evidence_payload())

    assert result.valid
    assert result.errors == []


def test_rejects_missing_release_evidence_fields():
    payload = build_evidence_template()

    result = validate_evidence(payload)

    assert not result.valid
    assert "preflight.run_id must be a GitHub run id" in result.errors
    assert "issueops.issue_url is required" in result.errors
    assert "extract.raw_payload_gcs_uri must be a gs:// URI" in result.errors
    assert "exports.fact_reviews.gcs_uri must be a gs:// URI" in result.errors


def test_requires_all_preserved_issue_commands():
    payload = complete_evidence_payload()
    payload["issueops"]["commands"] = ["/run-facility"]

    result = validate_evidence(payload)

    assert not result.valid
    assert "issueops.commands must include /run-reviews" in result.errors
    assert "issueops.commands must include /run-reviews-sequential" in result.errors
    assert "issueops.commands must include /run-reviews-relevance" in result.errors


def test_rejects_non_github_evidence_urls_and_non_numeric_run_ids():
    payload = complete_evidence_payload()
    payload["preflight"]["run_id"] = "run-1001"
    payload["preflight"]["summary_url"] = "https://example.com/actions/runs/1001"
    payload["issueops"]["issue_url"] = "https://github.com/mememori8888/other/issues/1"
    payload["load_transform"]["transform_run_id"] = "inline"

    result = validate_evidence(payload)

    assert not result.valid
    assert "preflight.run_id must be a GitHub run id" in result.errors
    assert "preflight.summary_url must be a https://github.com/mememori8888/1000man-programmer-project-v2 URL matching /actions/runs/\\d+$" in result.errors
    assert "issueops.issue_url must be a https://github.com/mememori8888/1000man-programmer-project-v2 URL matching /issues/\\d+$" in result.errors
    assert "load_transform.transform_run_id must be a GitHub run id" in result.errors


def test_evidence_cli_template_and_validate(tmp_path, capsys):
    evidence_path = tmp_path / "release-evidence.json"

    assert main(["template", "--output", str(evidence_path)]) == 0
    template_output = json.loads(capsys.readouterr().out)
    assert template_output["preflight"]["dry_run_artifact"] == "work-bigquery-dry-run.json"

    evidence_path.write_text(json.dumps(complete_evidence_payload()), encoding="utf-8")

    assert main(["validate", "--file", str(evidence_path)]) == 0
    result_output = json.loads(capsys.readouterr().out)
    assert result_output["valid"] is True
