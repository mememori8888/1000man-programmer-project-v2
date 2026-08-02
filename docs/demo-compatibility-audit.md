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
| `reviews_recent_with_relevance.yml` SERP rank enrichment | SERP raw response storage, bounded batch orchestration, and BigQuery rank fact transform are implemented as the v2 foundation |
| `serp_reviews_smoke.yml` diagnostics | Preserved via `.github/workflows/serp-reviews-smoke.yml` |
| `recover-run-artifacts.yml` CSV batch recovery | Replaced by `.github/workflows/raw-object-replay.yml` for GCS raw object replay and BigQuery re-transform |
| `generate-file-list.yml` / `docs/webapp/files.json` | Replaced by `docs/webapp/file-presets.json`, a curated public-safe candidate list that preserves WebApp selection ergonomics without exposing private repository contents |
| n8n local relevance workflow | Keep optional; do not make it part of the standard cloud path |

## Next compatibility targets

1. Verify the BigQuery recent-review target path against a real BrightData run and compare row counts with the old CSV outputs.
