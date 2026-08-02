# demo compatibility audit

Source inspected: `mememori8888/demo` at `e6a01b3` (`Build canonical Google Maps reviews URLs`).

## Preserved in v2

| demo capability | v2 status |
| --- | --- |
| WebApp creates GitHub Issues | Preserved via `docs/webapp/` |
| `/run-facility`, `/run-reviews`, `/run-reviews-sequential`, `/run-reviews-relevance`, `/承認` | Parsed by `src/elt_v2/issue_ops.py` and routed by `.github/workflows/issue-ops-elt.yml` |
| BrightData Dataset API extraction | Implemented in `elt-brightdata run-dataset` and `.github/workflows/brightdata-extract.yml` |
| Raw artifacts | Preserved as raw object artifacts, with optional GCS upload |
| CSV output compatibility | Implemented as BigQuery extract jobs to GCS via `.github/workflows/bigquery-export.yml` for review, facility, and relevance-rank mart tables |
| BigQuery transforms | Implemented via `sql/bigquery/*.sql` and `.github/workflows/bigquery-transform.yml` |
| Legacy CSV vs v2 mart verification | Implemented via `.github/workflows/compatibility-audit.yml` and `elt-bigquery audit-csv-compat`; `fail_on_diff` can turn key differences into a CI failure after the report is uploaded |

## Still thin or intentionally changed

| demo capability | v2 direction |
| --- | --- |
| `reviews_recent_with_relevance.yml` SERP rank enrichment | SERP raw response storage, bounded batch orchestration, and BigQuery rank fact transform are implemented as the v2 foundation |
| `serp_reviews_smoke.yml` diagnostics | Preserved via `.github/workflows/serp-reviews-smoke.yml` |
| `recover-run-artifacts.yml` CSV batch recovery | Replaced by `.github/workflows/raw-object-replay.yml` for GCS raw object replay and BigQuery re-transform |
| `generate-file-list.yml` / `docs/webapp/files.json` | Replaced by `docs/webapp/file-presets.json`, a curated public-safe candidate list that preserves WebApp selection ergonomics without exposing private repository contents |
| n8n local relevance workflow | Keep optional; do not make it part of the standard cloud path |

## Next compatibility targets

1. Run `.github/workflows/compatibility-audit.yml` after a real BrightData run with `fail_on_diff: true` and archive the generated report with the release evidence.
2. Export `fact_reviews`, `dim_facilities`, and `fact_review_relevance_ranks` through `.github/workflows/bigquery-export.yml` and compare the delivered CSV shape with the old demo outputs.

## Release evidence checklist

v2 を「demo 機能を損なわずに置き換えられる」と判断する前に、次の実行証跡を 1 つの release evidence として残します。

| Evidence | Required proof |
| --- | --- |
| Preflight | `v2 ELT preflight` の run ID と Summary。`work-bigquery-dry-run.json` artifact を保存し、GCS bucket、BigQuery dataset、標準 SQL dry-run が成功していること |
| IssueOps request | WebApp から作成した Issue URL。`/run-facility`, `/run-reviews`, `/run-reviews-sequential`, `/run-reviews-relevance` のうち対象 release で保証するコマンドと `/承認` コメント |
| Extract | IssueOps の最終コメント、BrightData workflow run ID、raw payload GCS URI、raw manifest GCS URI |
| Load and Transform | BigQuery raw table への load job ID、`elt-bigquery run-all-sql` または `bigquery-transform.yml` の run ID |
| CSV compatibility export | `fact_reviews`, `dim_facilities`, `fact_review_relevance_ranks` の GCS export URI と `bigquery-export.yml` の run ID |
| demo-vs-v2 audit | `compatibility-audit.yml` を `run_transform: true`、`fail_on_diff: true` で実行した run ID、Summary、`compatibility-audit.json` artifact |
| Exceptions | 差分が残る場合は、旧 demo の仕様差、v2 の意図的変更、追跡 Issue URL を明記する |

このチェックリストは削除判定ではなく、移行判定のためのものです。旧ファイルや旧 workflow は、上記証跡で代替機能が確認できるまで残します。

証跡 JSON のひな形は次のコマンドで作れます。

```powershell
$env:PYTHONPATH='src'
python -m elt_v2.evidence_cli template --output docs/release-evidence.json
```

実 run ID、Issue URL、GCS URI、artifact 名を埋めたら、次のコマンドで必須項目の抜けを確認します。

```powershell
$env:PYTHONPATH='src'
python -m elt_v2.evidence_cli validate --file docs/release-evidence.json
```
