# Operations Scripts

`ops/` contains downstream integration and maintenance utilities. The canonical
corpus pipeline now lives in `scripts/`; do not treat every script in this
directory as part of the current default build path.

## Current

| Script | Status | Purpose |
|---|---|---|
| `export_patra_darpan_data_js.py` | current | Reads `exports/index.tsv`, writes `web/assets/js/data.js`, and refreshes the local `web/assets/pdfs` symlink. |
| `sync_gcs.py` | manual operational utility | Compares local `corpus/ijhs/` and `corpus/other/` PDFs with the configured GCS bucket. Run `--diff` first; upload and orphan deletion modes are intentionally manual. |
| `generate_juni_embeds.py` | manual sidecar utility | Generates iframe snippets for the sibling JUNI site and the local iframe sandbox. This assumes a maintainer-local `~/projects/cahcblr.github.io` checkout. |

## Legacy / Retained For Reference

These scripts may still be useful for migration archaeology or one-off recovery,
but they are not part of the current canonical corpus workflow.

| Script | Legacy role | Current caution |
|---|---|---|
| `analyze_tsv.py` | Diagnostic duplicate/anomaly scan for the older `corpus/ijhs.tsv` flow. | Read-only, but its assumptions predate the current canonical build/report pipeline. |
| `dedupe_tsv.py` | Mutating duplicate cleanup for the older `corpus/ijhs.tsv` and `corpus/ijhs-classified.tsv` flow. | Do not run as-is in the current layout; `corpus/ijhs-classified.tsv` is now a legacy reference artifact, not a current root input. |
| `migrate_index.py` | One-time migration from `corpus/ijhs-classified.tsv` to `corpus/index.tsv`. | Stale for the current layout; canonical projection is now produced by `scripts/export_index_tsv.py` into `exports/index.tsv`. |

`ops/gcs-key.json`, if present locally, is an ignored credential file and should
not be committed.
