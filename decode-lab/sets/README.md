# Decode Lab Campaign Sets

A campaign set is a named, ordered list of canonical `doc_id` values used for
repeatable profiling, decoding, and audit runs.

Set files live in this directory and use one `doc_id` per non-empty,
non-comment line. Lines beginning with `#` are comments.

Example:

```text
# Purpose: confidence-building repeat operation.
1
Vol01_1_8_AKBag
```

Terminology:

- Campaign set: reusable document selection, for example `micro-2`.
- Run ID: one execution label, for example `flex-micro2-3flash-med`.
- Extractor: the decode method, for example `local` or `gemini:3-flash-med`.
- Profile: durable per-PDF facts stored in SQLite.

The set file is not run evidence and is not a cache. It is the human-readable
definition of what should be included in a named campaign.

## Generated Sets

Use `scripts/generate_campaign_sets.py` for lightweight exploratory set
creation from `exports/index.tsv` joined to the SQLite
`primary_pdf_profiles` view.

Example:

```bash
uv run python scripts/generate_campaign_sets.py astro math indic raster native 10 --name astro-math-indic-10
```

The positional words are hints. Unique partial hints are accepted, so `tab`
matches `tables`. Ambiguous partials fail.

The script prints the effective normalized recipe before writing files.
Existing `.txt` or `.notes.md` files are never overwritten unless `--force`
is supplied.
