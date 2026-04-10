# Legacy Pipeline Scripts

`pipeline/` contains the pre-SPASTA ingestion and enrichment scripts. These are
retained because they document useful operational knowledge and may still help
with migration archaeology or one-off recovery, but the current canonical corpus
pipeline entrypoints live in `scripts/`.

Do not run these scripts as the default corpus workflow. Several of them assume
the older layout where `corpus/index.tsv` and `corpus/ijhs-classified.tsv` were
current mutable artifacts.

## Legacy Roles

The purpose descriptions below are carried forward from the `main` branch README
and checked against the script headers.

| Script | Legacy role | Current caution |
|---|---|---|
| `01-scrape.py` | Scrapes IJHS metadata from the INSA portal and downloads IJHS PDFs into `corpus/ijhs/`. | Uses Selenium/Chrome and mutates the older `corpus/ijhs.tsv` plus local PDF directories. Not part of the current default canonical build. |
| `02-patch.py` | Applies known metadata fixes and CAHC-authorship tags to `corpus/ijhs.tsv`. | Mutates `corpus/ijhs.tsv` in place. Current root-input changes should be made deliberately in `corpus/` and validated through `scripts/`. |
| `03-classify.py` | Uses Gemini to classify IJHS papers by subject/category and produce classified outputs/reports. | Requires `GEMINI_API_KEY`; script comments still describe older scraped/classified artifact flow. Not part of the current default canonical build. |
| `04-compare.py` | Compares classification output with the legacy `p85` search view. | Contains maintainer-local path assumptions and reads older `.cache` artifacts. Treat as migration-audit reference only unless revived. |
| `05-import-cahcblr.py` | Imports non-IJHS metadata from the sibling `cahcblr.github.io` / JUNI markdown sources. | Assumes a maintainer-local sibling checkout and older `corpus/ijhs-classified.tsv` flow. Current curated inputs live in `corpus/curated-*.tsv`. |
| `bootstrap-ingest.py` | One-time utility to integrate existing JUNI `cached_papers/rni/` PDFs into the unified corpus architecture. | Writes older `corpus/index.tsv` / `corpus/other/` style targets. Retain for reference; do not run as part of the current default workflow. |

## Current Canonical Flow

Use the root-level documented sequence instead:

```bash
uv run python scripts/build_corpus_metadata.py
uv run python scripts/export_index_tsv.py
uv run python scripts/validate_legacy_index.py
uv run python scripts/audit_corpus_inputs.py
```

Then regenerate the Patra Darpan web payload when needed:

```bash
uv run python ops/export_patra_darpan_data_js.py
```
