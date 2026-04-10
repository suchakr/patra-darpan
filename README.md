# Patra Darpan

Patra Darpan is a corpus, projection, and web-access layer for scholarly
documents, with an initial focus on the Indian Journal of History of Science
and curated related material.

Its purpose is to make the corpus:
- easier to browse and search
- easier to maintain and extend
- more resilient when original source sites are slow, down, or inconsistent

The current architecture uses a cleaner canonical corpus layer with explicit
root inputs, canonical assembly in SQLite, compatibility projections such as
`exports/index.tsv`, and a separate Patra Darpan web payload build.

Patra Darpan does **not** own the shared PDF binaries in this repository.
In this repository layout, PDFs are served from the sibling `patra-darpan`
checkout.

## Status

Current milestone:
- root inputs are explicit and documented
- canonical corpus build works
- legacy-compatible `index.tsv` regeneration works from canonical root inputs
- Patra Darpan `data.js` can be regenerated from `exports/index.tsv`

Legacy scripts still exist in the repo, but the intended authority flow is now:

`root inputs -> canonical build -> validation/audit -> compatibility projections`

## Repository Layout

- `corpus/`
  root metadata inputs only
- `scripts/`
  canonical corpus pipeline entrypoints
- `pipeline/`
  legacy ingestion/enrichment scripts retained for reference; see
  `pipeline/README.md`
- `ops/`
  downstream integration utilities such as Patra Darpan payload export; see
  `ops/README.md` for current vs legacy script status
- `lib/`
  shared implementation code
- `exports/`
  generated compatibility outputs such as `index.tsv`
- `reports/`
  validation, audit, and migration reports
- `reference/legacy/`
  legacy comparison fixtures
- `.build~/`
  generated machine state, including the SQLite corpus build
- `scratch~/`
  untracked helpers and one-offs
- `web/`
  Patra Darpan SPA, Netlify function, and local web testing docs

## Root Inputs

See [corpus/README.md](corpus/README.md).

Current root metadata inputs are:
- `corpus/ijhs.tsv`
- `corpus/curated-pdfs.tsv`
- `corpus/curated-links.tsv`
- `corpus/cahc_authored_registry.txt`
- `corpus/cahc-pdf-mirrors.tsv`

Shared PDF asset roots live in the sibling `patra-darpan` checkout:
- `corpus/ijhs`
- `corpus/other`

## Common Commands

Run these from the repository root unless noted otherwise.

### Canonical Corpus

```bash
uv run python scripts/build_corpus_metadata.py
uv run python scripts/export_index_tsv.py
uv run python scripts/validate_legacy_index.py
uv run python scripts/audit_corpus_inputs.py
```

### Patra Darpan Web Payload

```bash
uv run python ops/export_patra_darpan_data_js.py
```

This reads `exports/index.tsv` and writes:
- `web/assets/js/data.js`
- `web/assets/pdfs` symlink to the shared PDF asset root

### Local Web Preview

```bash
cd web
uv run python -m http.server 8000
```

Then open:
- `http://127.0.0.1:8000`

For Netlify-function testing:

```bash
cd web
npm install
netlify dev
```

See [web/README.md](web/README.md).

## Branching From Here

If you branch from this repository state, treat these as frozen-for-now unless
your branch is intentionally architectural:

- root input contract under `corpus/`
- directory roles (`corpus/`, `scripts/`, `ops/`, `exports/`, `reports/`,
  `reference/legacy/`, `.build~/`)
- canonical `index.tsv` projection contract
- shared PDF asset root assumption via the sibling `patra-darpan` checkout

Before making changes, read:
- [README.md](README.md)
- [corpus/README.md](corpus/README.md)
- [docs/index-tsv-projection-contract.md](docs/index-tsv-projection-contract.md)
- [web/README.md](web/README.md) if you are touching the SPA or Netlify flow

From the repository root, verify the current baseline:

```bash
uv run python scripts/build_corpus_metadata.py
uv run python scripts/export_index_tsv.py
uv run python scripts/validate_legacy_index.py
uv run python scripts/audit_corpus_inputs.py
```

If you are touching Patra Darpan web behavior, also run:

```bash
uv run python ops/export_patra_darpan_data_js.py
cd web
uv run python -m http.server 8000
```

Use `netlify dev` from `web/` only when you need to test Netlify-function
behavior.

Prefer these boundaries:
- `scripts/` for canonical corpus pipeline steps
- `ops/` for downstream integration utilities
- `corpus/` for root metadata inputs only
- `exports/` and `reports/` for generated text artifacts

If your branch changes any frozen-for-now contract, document that explicitly in
`docs/spasta-corpus-decisions.md` or the relevant design doc.

## Adding New Items

There are three normal add paths.

### 1. New IJHS PDF-backed item

Use this when the item belongs in the portal/IJHS root:
- ensure the PDF exists in the shared asset root under `../patra-darpan/corpus/ijhs/`
- add or update the row in `corpus/ijhs.tsv`
- if the item has a CAHC/JU mirror, add it to `corpus/cahc-pdf-mirrors.tsv`
- if the item is CAHC-authored, add it to `corpus/cahc_authored_registry.txt`

Example workflow:

```bash
cp /path/to/IJHS_60_3_0.pdf ../patra-darpan/corpus/ijhs/
```

Append to `corpus/ijhs.tsv`:

```tsv
IJHS-60-2025-Issue-3	On mean motions in Indian astronomy	https://insa.nic.in/(S(...))/writereaddata/UpLoadedFiles/IJHS/IJHS_60_3_0.pdf	531	Anil Narayanan
```

If mirrored, append to `corpus/cahc-pdf-mirrors.tsv`:

```tsv
https://insa.nic.in/(S(...))/writereaddata/UpLoadedFiles/IJHS/IJHS_60_3_0.pdf	https://cahc.jainuniversity.ac.in/assets/cached_papers/rni/IJHS_60_3_0.pdf
```

Current convention:
- CAHC/JU mirror URLs usually take the form
  `https://cahc.jainuniversity.ac.in/assets/cached_papers/rni/<pdf>`
- on the current maintainer machine, that mirror is typically backed by copying
  the PDF into `~/projects/cahcblr.github.io/assets/cached_papers/rni/<pdf>`
- on another machine or clone, the developer is responsible for ensuring that a
  declared mirror URL is actually valid

If CAHC-authored, append to `corpus/cahc_authored_registry.txt`:

```text
IJHS_60_3_0.pdf
```

### 2. New curated PDF-backed item

Use this when the item is not part of portal IJHS ingest:
- place the PDF in the shared asset root under `../patra-darpan/corpus/other/`
- add the row to `corpus/curated-pdfs.tsv`
- if the item has a CAHC/JU mirror, add it to `corpus/cahc-pdf-mirrors.tsv`
- if the item is CAHC-authored, add it to `corpus/cahc_authored_registry.txt`

Example workflow:

```bash
cp /path/to/The_Scope_of_Ashtadashavarnana.pdf ../patra-darpan/corpus/other/
```

Append to `corpus/curated-pdfs.tsv`:

```tsv
Karnataka Sanskrit 8.1	The Scope of Aṣṭādaśavarṇana in the Mahākāvya Mathurābhyudaya	https://cahc.jainuniversity.ac.in/assets/cached_papers/rni/The_Scope_of_Ashtadashavarnana.pdf	320.0	2025.0	Shankar Rajaraman, R. S. Hariharan
```

If the mirror URL should be treated as a declared mirror of some other source
URL, append that pair to `corpus/cahc-pdf-mirrors.tsv`.

Current convention:
- CAHC/JU mirror URLs usually take the form
  `https://cahc.jainuniversity.ac.in/assets/cached_papers/rni/<pdf>`
- on the current maintainer machine, that mirror is typically backed by copying
  the PDF into `~/projects/cahcblr.github.io/assets/cached_papers/rni/<pdf>`
- on another machine or clone, the developer is responsible for ensuring that a
  declared mirror URL is actually valid

If CAHC-authored, append to `corpus/cahc_authored_registry.txt`:

```text
The_Scope_of_Ashtadashavarnana.pdf
```

### 3. New URL-only item

Use this when there is no managed local PDF:
- add the row to `corpus/curated-links.tsv`
- if the item is CAHC-authored, add it to `corpus/cahc_authored_registry.txt`

Example `corpus/curated-links.tsv` row:

```tsv
SwarajyaMag	Did India Lack Historical Consciousness, Or Is It Just That India Understood Time Differently?	https://swarajyamag.com/ideas/did-india-lack-historical-consciousness-or-is-it-just-that-india-understood-time-differently	2026	R. S. Hariharan
```

### After Adding

From the repository root:

```bash
uv run python scripts/build_corpus_metadata.py
uv run python scripts/export_index_tsv.py
uv run python scripts/validate_legacy_index.py
uv run python scripts/audit_corpus_inputs.py
uv run python ops/export_patra_darpan_data_js.py
```

### Deleting Or Retiring Items

Treat deletion as higher-risk than addition.

Do not casually remove root-input rows, shared PDFs, or GCS objects. Prefer to:
- first classify the item as duplicate, obsolete, or bad
- keep a report or manifest if shared assets or GCS objects will be removed
- rerun export and audit after any intentional deletion

## Documentation Map

- [corpus/README.md](corpus/README.md)
  root-input contract and file schemas
- [docs/spasta-corpus-prd.md](docs/spasta-corpus-prd.md)
  product intent and migration rationale
- [docs/spasta-corpus-technical-design.md](docs/spasta-corpus-technical-design.md)
  technical architecture and layer model
- [docs/spasta-corpus-decisions.md](docs/spasta-corpus-decisions.md)
  durable design and tactical decisions
- [docs/index-tsv-projection-contract.md](docs/index-tsv-projection-contract.md)
  `index.tsv` compatibility projection contract
- [web/README.md](web/README.md)
  local web runtime, Netlify dev/deploy, and link behavior

## Environment

Python commands in this repository should use `uv run python ...`, not system
Python.

## License

Code in this repository is licensed under the MIT License. PDF/content rights
vary by source and remain with their respective publishers, repositories, or
mirror providers.
