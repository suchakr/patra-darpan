# Repeatable retrieval index build

The retrieval MCP container is read-only. Index materialization is a separate
one-shot Compose job so a service restart does not re-embed the corpus.

## Default release scope

The builder reads the pinned Sanchaya checkout and creates one manifest with:

- all exported Patra Darpan papers (`RETRIEVAL_PAPER_SCOPE=all`, currently 120);
- every UTF-8 text file under `Jyotisham/`;
- the six Jyotisha anchor texts used by the demo questions.

Set `RETRIEVAL_PAPER_SCOPE=audit` for the smaller 29-paper calibration release.
Set `RETRIEVAL_SANCHAYA_SCOPE=probe` to restore the original probe set.

## Build lifecycle

The same commands run on a developer machine and on the production host:

```bash
make build
make index
make inspect
make smoke
```

The Makefile starts the Compose-owned Qdrant service and waits for its HTTP
endpoint before the builder runs. Production uses the same targets with
`PROD=1` and defaults to `/etc/patra-darpan/retrieval.env`. Set `ENV_FILE=...`
to override that path. The production overlay keeps Qdrant private and supplies
its service URL.

The builder performs, in order:

1. source manifest and content-hash validation;
2. deterministic chunk generation;
3. ontology-driven entity mentions and registry JSONL;
4. full E5 embedding into a commit-scoped Qdrant collection;
5. immutable release assembly and activation.

The release ID and collection name include the Sanchaya commit and source
scope. Re-running an already active release is a no-op. To rebuild, publish a
new `--release-id` (normally by advancing the source revision); the builder
refuses to delete the active release. `--force` is only for replacing an
inactive, abandoned release directory.

Qdrant storage and the release directory are persistent mounts. The MCP
service therefore reuses the completed vector collection after restarts and
does not need the Sanchaya checkout at query time except for safe passage/media
resolution paths already declared by the release.
