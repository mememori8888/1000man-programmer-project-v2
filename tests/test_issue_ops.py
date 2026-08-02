from __future__ import annotations

import json

from elt_v2.issue_ops import parse_issue_request, to_payload_json, validate_issue_request


def test_parses_reviews_relevance_before_generic_reviews():
    body = """/run-reviews-relevance

```json
{"csv_file":"results/dental.csv","output_file":"results/reviews.csv","days_back":"30","rows_per_batch":"500","api_batch_size":"50","max_wait_minutes":"90","dataset_id":"gd_luzfs1dn2oa0teb81","skip_column":"web","relevance_rank_limit":"10","serp_max_workers":"3","serp_zone_name":"serp_api2","summary_file":"results/summary.csv"}
```
"""
    request = parse_issue_request(body)

    assert request.command == "/run-reviews-relevance"
    assert request.workflow_type == "reviews_recent_relevance"
    assert request.dataset_kind == "reviews"
    assert validate_issue_request(request) == []


def test_parses_facility_as_facilities_dataset():
    request = parse_issue_request("/run-facility\n\n```json\n{}\n```")

    assert request.workflow_type == "facility"
    assert request.dataset_kind == "facilities"
    assert json.loads(to_payload_json(request))["workflow_type"] == "facility"


def test_validates_required_sequential_fields():
    request = parse_issue_request("/run-reviews-sequential\n\n```json\n{}\n```")

    errors = validate_issue_request(request)

    assert "csv_file is required" in errors
    assert "output_file is required" in errors


def test_rejects_unsafe_private_csv_paths():
    body = """/run-reviews-sequential

```json
{"csv_file":"../secrets.csv","output_file":"results/reviews.txt","days_back":"30","rows_per_batch":"500","api_batch_size":"50","max_wait_minutes":"90","dataset_id":"gd_luzfs1dn2oa0teb81","skip_column":"web"}
```
"""
    errors = validate_issue_request(parse_issue_request(body))

    assert "csv_file must be a safe CSV path under settings/ or results/" in errors
    assert "output_file must end with .csv" in errors


def test_validates_nested_custom_settings_paths():
    body = """/run-facility

```json
{"csv_file":"settings/address.csv","custom_settings":{"address_csv_path":"/tmp/address.csv"}}
```
"""
    errors = validate_issue_request(parse_issue_request(body))

    assert "address_csv_path must be a safe CSV path under settings/ or results/" in errors


def test_rejects_non_object_custom_settings():
    body = """/run-reviews

```json
{"fid_file":"results/fid.csv","custom_settings":"settings/review.csv"}
```
"""
    errors = validate_issue_request(parse_issue_request(body))

    assert "custom_settings must be an object" in errors
