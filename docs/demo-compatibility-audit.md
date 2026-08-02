# demo compatibility audit

Source inspected: `mememori8888/demo` at `e6a01b3` (`Build canonical Google Maps reviews URLs`).

## Preserved in v2

| demo capability | v2 status |
| --- | --- |
| WebApp creates GitHub Issues | Preserved via `docs/webapp/` |
| `/run-facility`, `/run-reviews`, `/run-reviews-sequential`, `/run-reviews-relevance`, `/承認` | Parsed by `src/elt_v2/issue_ops.py` and routed by `.github/workflows/issue-ops-elt.yml` |
| BrightData Dataset API extraction | Implemented in `elt-brightdata run-dataset` and `.github/workflows/brightdata-extract.yml` |
| Raw artifacts | Preserved as raw object artifacts, with optional GCS upload |
| CSV output compatibility | Implemented as BigQuery extract jobs to GCS via `.github/workflows/bigquery-export.yml` |
| BigQuery transforms | Implemented via `sql/bigquery/*.sql` and `.github/workflows/bigquery-transform.yml` |

## Still thin or intentionally changed

| demo capability | v2 direction |
| --- | --- |
| `reviews_recent_with_relevance.yml` SERP rank enrichment | SERP raw response storage and BigQuery rank fact transform are implemented as the v2 foundation |
| `serp_reviews_smoke.yml` diagnostics | Preserved via `.github/workflows/serp-reviews-smoke.yml` |
| `recover-run-artifacts.yml` CSV batch recovery | Replaced by `.github/workflows/raw-object-replay.yml` for GCS raw object replay and BigQuery re-transform |
| `generate-file-list.yml` / `docs/webapp/files.json` | v2 WebApp uses static defaults today; dynamic private-data file listing remains a compatibility gap |
| n8n local relevance workflow | Keep optional; do not make it part of the standard cloud path |

## Next compatibility targets

1. Add dynamic file listing for WebApp inputs without exposing private repository contents publicly.
2. Add an orchestration layer that runs SERP relevance extraction for all facilities with recent Dataset reviews.
