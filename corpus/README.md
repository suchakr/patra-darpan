# Corpus Root Input Contract

This directory defines the root inputs for the current canonical corpus build.

Root inputs are the files and asset locations that canonical assembly reads directly.
Derived artifacts do not belong to the root-input set.

## Root Inputs

### Shared PDF asset roots
These are external shared asset roots owned by the sibling `patra-darpan`
checkout. They are not git-managed here.

- `../patra-darpan/corpus/ijhs/`
  Role: local PDF asset root for portal-derived IJHS papers
- `../patra-darpan/corpus/other/`
  Role: local PDF asset root for curated non-IJHS papers

### Git-managed finite metadata files in this repository
These files are root inputs for canonical assembly and are git-managed here.

- [ijhs.tsv](ijhs.tsv)
  Role: portal-derived metadata root for IJHS papers
  Owner: upstream refresh by `01-scrape.py`, but the canonical build treats the
  file itself as an external root input

- [cahc_authored_registry.txt](cahc_authored_registry.txt)
  Role: narrow manual patch input for CAHC authorship tagging

- [cahc-pdf-mirrors.tsv](cahc-pdf-mirrors.tsv)
  Role: explicit mapping from source PDF URLs to CAHC-managed mirror URLs

- [curated-pdfs.tsv](curated-pdfs.tsv)
  Role: curated metadata root for PDFs stored under `../patra-darpan/corpus/other/`

- [curated-links.tsv](curated-links.tsv)
  Role: curated metadata root for URL-only corpus entries

## Not Root Inputs

These files are retained under `reference/legacy/` for migration comparison, but
they are not root inputs for the new canonical build.

- [reference/legacy/ijhs-classified.tsv](../reference/legacy/ijhs-classified.tsv)
  Role: derived enrichment over `ijhs.tsv`

- [reference/legacy/index.tsv](../reference/legacy/index.tsv)
  Role: legacy unified projection and migration comparison target

## Transitional Note

The current `main` branch has a historically messy layout where `ijhs.tsv` acts as a sum of portal-derived metadata and additional non-IJHS metadata imported through legacy flows.

The cleanup direction is:
- keep `ijhs.tsv` as the portal-derived root metadata input
- move non-IJHS local-PDF metadata into `curated-pdfs.tsv`
- move URL-only curated entries into `curated-links.tsv`
- treat `ijhs-classified.tsv` and `index.tsv` as derived/migration files under `reference/legacy/`, not root inputs

## Expected Schemas

### `ijhs.tsv`
Current root columns:
- `journal`
- `paper`
- `url`
- `size_in_kb`
- `author`

Working expectation:
- this file contains the portal-derived metadata root used by canonical assembly
- `year` is derived during canonical assembly from the stable IJHS journal naming convention
- CAHC mirror and authorship signals do not live here
- non-IJHS rows that previously lived here as migration baggage have been moved to `curated-pdfs.tsv`

### `cahc_authored_registry.txt`
Current format:
- one filename fragment or URL fragment per line
- `#` starts a comment

Working expectation:
- this remains a narrow manual patch input for CAHC authorship
- it is not a general metadata store

### `cahc-pdf-mirrors.tsv`
Current root columns:
- `source_url`
- `mirror_url`

Working expectation:
- one row declares that a source PDF URL has a CAHC-managed mirror URL
- this is the root-input home for what used to be carried as `ju_url`
- mirror information is projected into asset references, not treated as document metadata

### `curated-pdfs.tsv`
Current root columns:
- `journal`
- `paper`
- `url`
- `size_in_kb`
- `year`
- `author`

Working expectation:
- one row describes one curated local PDF intended to map to
  `../patra-darpan/corpus/other/`
- `year` is explicit here because it is not safely derivable from journal naming

### `curated-links.tsv`
Current root columns:
- `journal`
- `paper`
- `url`
- `year`
- `author`

Working expectation:
- one row describes one URL-only corpus entry
- no local PDF is assumed

## Projection Intent

The root inputs may be cleaner and smaller than legacy `index.tsv`, as long as the canonical build can reliably project a legacy-compatible `index.tsv`.

## Assembly Boundary

The canonical corpus build is responsible for:
- reading these root inputs
- normalizing them
- assembling canonical corpus state
- validating and projecting outputs

The canonical corpus build is not responsible for:
- scraping INSA or any other live site
- guaranteeing the health of upstream refresh utilities such as `01-scrape.py`
- managing the shared PDF asset roots themselves
