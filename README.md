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
- the deployed retrieval and MCP system is documented in
  [`docs/retrieval/README.md`](docs/retrieval/README.md)

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
- `tools/`
  local human/agent workbenches outside the canonical pipeline; see
  `tools/README.md`
- `lib/`
  shared implementation code
- `exports/`
  generated compatibility outputs such as `index.tsv`
- `reports/`
  validation, audit, and migration reports
- `docs/retrieval/`
  current retrieval architecture, contracts, operations, and release schemas
- `docs/iscls/`
  historical pilot PRD and staged implementation record
- `reports/iscls/`
  one-off retrieval bakeoff and ontology-generation records
- `ontology/`
  versioned, repository-owned ontology snapshots
- `reference/legacy/`
  legacy comparison fixtures
- `.build~/`
  generated machine state, including the SQLite corpus build
- `scratch~/`
  untracked helpers and one-offs
- `web/`
  Patra Darpan SPA, Netlify function, and local web testing docs
- `deploy.sh`
  root wrapper for corpus preparation, GCS synchronization, and Netlify modes

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

## Retrieval and MCP

The retrieval system builds a composite release catalog plus three projections
from one reviewed source set:

- a read-only SQLite catalog covering Patra Darpan papers and release-scoped
  Sanchaya text files
- a Zoekt lexical index (the existing `sanchaya-zoekt` project)
- an E5 semantic vector index in Qdrant
- a v0.3 ontology-driven entity and mention projection

A read-only MCP server adapts those projections for ChatGPT, Codex, Claude, and
other MCP clients. The chat host owns conversation and answer synthesis; the
adapters own bounded retrieval. Catalog, indexed-content, and entity coverage
are reported separately.

The online MCP applications remain HTTP inside the private Docker network.
Caddy provides the public HTTPS/OAuth boundary at `/mcp`; the raw Zoekt RPC and
the data services remain private.

`make help` is the command entry point for both development and production.
The Makefile, Compose files, and checked-in environment examples are the
authoritative operational sources.

Start with [`docs/retrieval/README.md`](docs/retrieval/README.md) for the current
architecture, contracts, operations, authentication model, and decisions.
[`docs/iscls/README.md`](docs/iscls/README.md) retains the pilot history.

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
- `web/assets/js/p60.js`
- `web/assets/pdfs` symlink to the shared PDF asset root

### Local Web Preview

```bash
cd web
uv run python -m http.server 8000
```

Then open:
- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/p60-projection-sandbox.html` to inspect the generated
  CAHC `P60` projection

For Netlify-function testing:

```bash
npm --prefix web install
./deploy.sh local
```

See [web/README.md](web/README.md).

### Prepare And Deploy

Use the root deployment wrapper for corpus preparation, GCS synchronization,
local Netlify testing, and Netlify deploys:

```bash
./deploy.sh prepare
./deploy.sh gcs-sync
./deploy.sh local
./deploy.sh stage
./deploy.sh prod
```

`prepare` rebuilds the canonical corpus and projections, runs validation and
audit commands, checks the generated JavaScript, and reports GCS drift. It does
not upload PDFs or deploy the site.

`gcs-sync` is the explicit mutating GCS operation. It shows the diff, asks for
confirmation, uploads pending PDFs, and finishes with a read-only consistency
check. Netlify deployment never uploads PDFs implicitly.

`stage` creates a Netlify preview deploy. `prod` checks the generated
JavaScript, verifies that `web/` is linked to the expected Patra Darpan site,
and blocks when local PDFs have not been uploaded to GCS. Git branch and
worktree state are displayed but remain advisory, which permits intentionally
decoupled commits and deploys. Use the stricter release policy when needed:

```bash
./deploy.sh prod --strict
```

Strict production deployment requires branch `main` and a clean worktree.
Both stage and production deploy messages record the current branch, commit,
and whether the worktree was dirty. Pass additional Netlify arguments after
`--`, for example:

```bash
./deploy.sh stage -- --message "corpus preview"
```

Local mode defaults to `http://127.0.0.1:8890/` with internal static port
`8891`. If either the public port or
Netlify's internal static-server port is occupied, the wrapper selects the next
available port inside this project's reserved `8890`-`8899` block and prints
the resolved URL. Use `--port` or `--static-port` to choose different starting
ports. The older `--target-port` spelling remains an
accepted wrapper alias, but Netlify's simple static server requires its
`staticServerPort` setting internally.

The linked production site ID is pinned by the wrapper. A different expected
site may be supplied explicitly through `PATRA_DARPAN_NETLIFY_SITE_ID`.

For automation and deployment checks, the GCS utility also provides a
read-only exit-status contract:

```bash
uv run python ops/sync_gcs.py --check
```

It exits nonzero when local corpus roots are missing, PDFs need to be uploaded,
or GCS cannot be queried. Remote orphans are reported as warnings because they
do not make currently published corpus links unavailable.

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

### Worktree Policy

Default to a fresh worktree for new feature work. The local asset symlink setup
is reproducible through the web payload export, so do not repurpose an old
feature worktree as the normal workflow.

Example:

```bash
git worktree add ../patra-darpan-cahcportal -b feat/wire-cahcportal main
cd ../patra-darpan-cahcportal
uv run python ops/export_patra_darpan_data_js.py
```

This should recreate `web/assets/js/data.js` and the `web/assets/pdfs` symlink
from the documented shared asset-root assumptions. If this fails, treat it as a
bootstrap or documentation problem to fix, not as a reason to normalize
directory reuse.

Before creating, reusing, or deleting worktrees, check:

```bash
git status --short --branch
git worktree list
git branch --merged main
```

Notes for humans and agents:
- a `+` next to a branch in `git branch` means that branch is checked out in
  another worktree
- do not try to check out `main` in a secondary worktree while `main` is already
  checked out in the primary worktree
- use `git worktree move` if a worktree directory must be renamed
- delete merged feature branches with `git branch -d <branch>` only after they
  are no longer checked out in any worktree
- temporary `safe-main-before-*` branches are acceptable around merges, but
  should be deleted once the merge is verified and no longer needs that rollback
  point

Repurposing an existing worktree is only a temporary local workaround when fresh
setup is broken, slow, or blocked by local-only state. It should not become the
canonical workflow.

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

Append to `corpus/curated-pdfs.tsv`. Set the optional trailing `published_on`
field to an authoritative `YYYY-MM-DD` date when one is available:

```tsv
Karnataka Sanskrit 8.1	The Scope of Aṣṭādaśavarṇana in the Mahākāvya Mathurābhyudaya	https://cahc.jainuniversity.ac.in/assets/cached_papers/rni/The_Scope_of_Ashtadashavarnana.pdf	320.0	2025.0	R. S. Hariharan
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

Example `corpus/curated-links.tsv` row with its authoritative publication
date:

```tsv
SwarajyaMag	Did India Lack Historical Consciousness, Or Is It Just That India Understood Time Differently?	https://swarajyamag.com/ideas/did-india-lack-historical-consciousness-or-is-it-just-that-india-understood-time-differently	2026	R. S. Hariharan	2026-03-15
```

### After Adding

From the repository root:

```bash
./deploy.sh prepare
```

For a PDF-backed addition, follow `prepare` with `./deploy.sh gcs-sync`. URL-only
entries do not require a GCS upload.

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
- [docs/cahc-p60-projection-prd.md](docs/cahc-p60-projection-prd.md)
  CAHC `P60` projection and `P85` cleanup plan
- [web/README.md](web/README.md)
  local web runtime, Netlify dev/deploy, and link behavior
- [docs/retrieval/README.md](docs/retrieval/README.md)
  current retrieval architecture, contracts, operations, and authentication
- [docs/iscls/README.md](docs/iscls/README.md)
  historical ISCLS pilot PRD, implementation plan, and experiment references

## Environment

Python commands in this repository should use `uv run python ...`, not system
Python.

## License

Code in this repository is licensed under the MIT License. PDF/content rights
vary by source and remain with their respective publishers, repositories, or
mirror providers.
