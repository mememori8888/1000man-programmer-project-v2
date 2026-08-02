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
