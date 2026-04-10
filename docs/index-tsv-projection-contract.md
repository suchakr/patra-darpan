# `index.tsv` Projection Contract

## Purpose
`exports/index.tsv` is a compatibility projection from canonical corpus state.

Its job is to:
- preserve the legacy `index.tsv` column shape
- remain easy for downstream Patra Darpan code to consume
- allow selective quality improvements where canonical metadata is more correct

The root inputs do not need to resemble legacy `index.tsv`, as long as the
canonical build can reliably project a legacy-compatible `index.tsv`.

## Status
This contract is the working rule for phase 1.

`index.tsv` should be:
- structurally compatible with `reference/legacy/index.tsv`
- semantically compatible by default
- allowed to deviate only where the new corpus is intentionally more correct or
  includes intentionally added rows

## Field Contract

| Field | Canonical derivation | Parity class | Working rule |
| --- | --- | --- | --- |
| `journal` | `documents.journal_label` | must match legacy by default | Preserve legacy text unless an intentional metadata correction is made. |
| `paper` | `documents.title` | must match legacy by default | Preserve legacy text unless an intentional metadata correction is made. |
| `subject` | derived enrichment, not root metadata | deferred enrichment | Fill from legacy-derived enrichment first; later rewriteable by a better classifier. |
| `category` | derived enrichment, not root metadata | deferred enrichment | Same rule as `subject`. |
| `author` | `documents.author_display` | must match legacy by default | Blank procedural entries are acceptable when that is the honest bibliographic state. |
| `url` | primary asset `remote_url` | must match legacy by default | This is the primary source URL, not the mirror URL. |
| `size_in_kb` | raw source metadata for PDFs; compatibility value for links | must match legacy by default | Keep as a projection field, not a canonical truth field. |
| `year` | canonical year (`IJHS` derived from `journal`; curated from root input) | may intentionally improve | Correctness is preferred over reproducing legacy blanks. |
| `ju_url` | mirror asset `remote_url` | must match legacy by default | This remains a compatibility field backed by mirror registry data. |
| `cahc_authored` | registry-derived label | must match legacy by default | This is a curated label, not a root bibliographic fact. |
| `entry_type` | `documents.entry_type` | must match legacy by default | Current values are `pdf` and `link`. |
| `source` | projection-only mapping from internal provenance | must match legacy vocabulary | Do not expose internal labels like `portal_ijhs` or `curated_pdf` directly. |
| `gcs_key` | primary asset `gcs_key` | must match legacy by default | Cleaned key differences are acceptable when they follow intentional duplicate cleanup or newly added rows. |
| `gcs_synced` | projection compatibility value | must match legacy by default | Keep `false` everywhere until this field is intentionally redefined. |

## Internal vs External Source Labels
Internal provenance belongs in canonical state:
- `documents.source_root`
- `document_sources.source_type`

The `index.tsv` `source` column is a compatibility projection and should use
downstream-facing labels rather than internal ones.

Current working direction:
- `portal_ijhs_metadata` -> legacy-facing portal label
- `curated_pdf_metadata` -> legacy-facing curated-PDF label
- `curated_link_metadata` -> host-specific legacy-facing label where needed

This mapping should be explicit in projection code.

## Acceptance Criteria

### Structural parity
Must hold:
- same header as `reference/legacy/index.tsv`
- one row per canonical document intended for legacy-style export
- stable ordering policy

### Compatibility parity
Should hold for legacy-covered rows:
- `journal`
- `paper`
- `author`
- `url`
- `ju_url`
- `cahc_authored`
- `entry_type`
- `source`
- `gcs_key`
- `gcs_synced`

### Acceptable intentional deviations
Allowed when documented:
- corrected `year`
- corrected title or author text
- cleaned duplicate-related asset keys or paths
- intentionally added corpus rows not present in legacy

### Temporary known gap
Current phase-1 known gap:
- `subject`
- `category`

These should not remain blank forever, but they do not block the canonical
substrate. The next parity-safe step is to project them from legacy-derived
enrichment before designing a better annotation pipeline.
