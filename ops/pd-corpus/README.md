# Patra Darpan Corpus Snapshot

Build and sync the latest browsable Patra Darpan corpus snapshot for Google
Drive distribution.

Generated output:

```text
pd-corpus~/
```

This directory is not source. It is rebuilt from the current local Patra Darpan
metadata, web assets, and shared PDF asset root.

## Build

```bash
uv run python ops/pd-corpus/build_snapshot.py
```

The builder hardlinks PDFs into `pd-corpus~/pdfs/` by default. If hardlinking is
not available, it fails instead of silently copying the corpus.

## Sync

```bash
ops/pd-corpus/sync_snapshot.sh
```

Default target:

```text
sccgdrive:pd-corpus/
```

Override the target when needed:

```bash
ops/pd-corpus/sync_snapshot.sh sccgdrive:some-other-folder/
```

