# PRD: Patra Darpan Corpus Snapshot

## Status
Draft

## Owner
Patra Darpan / CAHC corpus engineering

## Summary
The Patra Darpan corpus snapshot is a generated, browsable distribution tree
for sharing the current local Patra Darpan corpus with non-developer users.

The snapshot is not a new source of truth. It is built from the current local
metadata, web projections, and shared PDF asset roots. Those local sources are
also reflected in GCS, but GCS is not the input for this packaging flow.

The snapshot should be easy to copy to Google Drive with `rclone`, easy for a
recipient to download as a Drive folder, and usable by opening `index.html`
directly from a local filesystem. Users should not need Git, GCS credentials,
`http.server`, Netlify, or command-line tooling to browse and download papers.

## Problem Statement
Patra Darpan currently works well as a web access layer and as a local
maintainer workflow, but neither mode is ideal for sharing the whole corpus
with a non-developer recipient.

Current pain points:
- paper-by-paper download through the live Patra Darpan interface is
  impractical for corpus-scale transfer
- exposing a GCS bucket is operationally awkward for users who are not active
  developers
- GitHub is not suitable for the PDF binaries
- a local web server requirement would make the handoff less approachable
- naive release folders or zip files can duplicate the entire PDF corpus and
  waste local and remote storage

The needed artifact is a space-conscious, generated "latest snapshot" that can
be synced to Google Drive and downloaded by users as a normal folder.

## Goals
- Build one current, latest-only browsable corpus snapshot.
- Use current local sources as the source of truth.
- Share through Google Drive using `rclone`.
- Let users open `index.html` directly after downloading the folder.
- Support browsing/searching metadata and opening PDFs by relative local paths.
- Include metadata files for programmatic use.
- Avoid duplicate PDF storage in local staging.
- Avoid local zip generation by default; rely on Google Drive folder download
  zipping when users want a single download.
- Keep generated corpus output out of git.
- Keep build/sync scripts in git under a durable operational home.
- Preserve a human-readable release log instead of datewise release trees.

## Non-Goals
- Creating dated immutable releases.
- Creating or uploading a local mega zip by default.
- Making Google Drive behave like a static web host.
- Replacing the live Patra Darpan site or Netlify deployment flow.
- Replacing GCS as a reflected archival store.
- Moving the canonical metadata or PDF asset roots.
- Asking recipients to run a local server.
- Supporting incremental multi-version diffs in phase 1.

## Users And Stakeholders
- Non-developer corpus recipients who need a full local copy.
- Researchers who want paper-by-paper access after downloading the corpus
  folder.
- Maintainers who need a repeatable, low-risk packaging and sync workflow.
- Future agents or scripts that consume exported metadata outside the live web
  app.

## Source Of Truth
The snapshot is generated from current local sources:

```text
corpus/ijhs.tsv
corpus/curated-pdfs.tsv
corpus/curated-links.tsv
corpus/cahc-pdf-mirrors.tsv
corpus/cahc_authored_registry.txt
exports/index.tsv
web/assets/js/data.js
web/assets/js/p60.js
web/assets/css/
../patra-darpan/corpus/ijhs/
../patra-darpan/corpus/other/
```

The exact shared PDF asset root remains configurable through the existing
asset-root conventions. The expected default is the sibling
`../patra-darpan/corpus` tree.

GCS may contain a reflected copy of these assets, but this feature does not
build from GCS.

## Directory Contract
Generated snapshot root:

```text
pd-corpus~/
  index.html
  README.html
  RELEASE_LOG.md
  metadata/
    manifest.json
    index.tsv
    corpus.jsonl
    checksums.sha256
    root-inputs/
      ijhs.tsv
      curated-pdfs.tsv
      curated-links.tsv
      cahc-pdf-mirrors.tsv
      cahc_authored_registry.txt
  assets/
    css/
    js/
      data.js
      p60.js
      offline-browse.js
  pdfs/
    ijhs/
    other/
```

`pd-corpus~` is generated and not git-managed. The trailing `~` is intentional:
it matches the repository's generated-directory convention and visually warns
maintainers that the tree can be rebuilt.

Git-managed operational scripts:

```text
ops/pd-corpus/
  README.md
  build_snapshot.py
  sync_snapshot.sh
```

## Google Drive Contract
Default remote target:

```text
sccgdrive:pd-corpus/
```

Remote layout should mirror `pd-corpus~`:

```text
pd-corpus/
  index.html
  README.html
  RELEASE_LOG.md
  metadata/
  assets/
  pdfs/
```

There is only one latest snapshot. The release log records rebuild history.
The Drive folder itself is the user-facing distribution surface. If a user
chooses "Download" in Google Drive, Drive can zip the folder for them.

## Build Workflow
Primary build command:

```bash
uv run python ops/pd-corpus/build_snapshot.py
```

Primary sync command:

```bash
ops/pd-corpus/sync_snapshot.sh
```

The sync script defaults to:

```bash
rclone sync pd-corpus~ sccgdrive:pd-corpus/ --progress
```

It may accept an optional target override:

```bash
ops/pd-corpus/sync_snapshot.sh sccgdrive:some-other-folder/
```

## Space Efficiency
PDFs in `pd-corpus~/pdfs/` must be hard links to the local source PDFs by
default, not copied bytes.

Hard links are preferred over symbolic links because:
- they appear as normal files to browsers, Finder, Google Drive, and `rclone`
- they do not create broken links when downloaded
- Google Drive has no POSIX symlink equivalent
- they avoid `rclone` symlink/dereference ambiguity
- they avoid duplicate local disk blocks when source and destination are on the
  same filesystem

If hard linking fails, the builder should fail loudly by default. A future
`--copy-pdfs` escape hatch may be added, but copying PDFs must never happen
silently.

No local zip is produced by default. A zip would duplicate the corpus locally
and remotely, and Google Drive already provides folder download zipping for
recipients.

## Offline Browse Requirements
`pd-corpus~/index.html` must work when opened directly as a local file.

The offline browser should:
- load local static JavaScript and CSS without a server
- use generated metadata from local files already loaded by script tags
- link PDFs through relative paths such as `pdfs/ijhs/<filename>.pdf`
- support basic search and browsing comparable to the current Patra Darpan
  local interface
- avoid `fetch()` for required metadata unless file-mode compatibility is
  verified across target browsers
- avoid Netlify functions, signed URLs, GCS access, and runtime server
  detection

The implementation should reuse the current Patra Darpan UI and data payload
where practical, but file-mode reliability is more important than preserving
every live-site behavior.

## Metadata Requirements
The snapshot must include:
- `metadata/index.tsv` copied from the current generated export
- `metadata/corpus.jsonl` with one row per corpus item
- `metadata/manifest.json` with snapshot-level provenance
- `metadata/checksums.sha256` for metadata files and PDFs
- `metadata/root-inputs/` copies of the root metadata inputs

`manifest.json` should include at least:
- generated timestamp
- git commit, when available
- source PDF root
- row count
- PDF count by collection
- total PDF bytes
- missing PDF count
- builder script version or path
- sync target hint, if supplied

## Release Log
`RELEASE_LOG.md` records latest snapshot rebuilds. It replaces dated release
directories.

Each entry should include:
- timestamp
- git commit, when available
- row count
- PDF count
- total PDF bytes
- missing PDF count
- notes or warnings

The log is part of the generated snapshot and is synced to Drive.

## Validation
The builder should fail on:
- missing required metadata inputs
- missing `exports/index.tsv`
- missing required web assets
- missing shared PDF asset root
- hardlink failure, unless an explicit copy mode exists and is requested
- generated PDF links that do not resolve locally

The builder should report:
- total corpus rows
- PDF-backed rows
- URL-only rows
- local PDFs linked
- metadata files written
- checksum file path
- output root

## Open Questions
- Should the offline browser be a lightly patched copy of `web/index.html`, or
  a smaller purpose-built static browser that consumes `data.js`?
- Should checksums cover every PDF on every build, or should a cached checksum
  manifest be introduced if hashing becomes slow?
- Should the sync script run a dry-run by default before destructive remote
  sync, or should it match normal `rclone sync` behavior and require operator
  care?
