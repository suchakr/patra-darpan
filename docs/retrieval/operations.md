# Retrieval operations

## Command model

Run commands from the Patra Darpan semantic checkout. The Makefile selects the
production environment automatically when `/etc/patra-darpan/retrieval.env`
exists; otherwise it uses the repository `.env`. `ENV_FILE=...` overrides that
selection.

Only the guarded first-time setup uses `PROD=1`:

```bash
make PROD=1 prod-env
```

After that, development and production use the same target names. `make help`
is the authoritative target list.

## Environment

Development starts from `retrieval.env.example`, copied to the untracked `.env`
beside the Makefile. Production starts from `retrieval.env.prod.example`, copied
once by `make PROD=1 prod-env` to the host-only env file.

The important host paths are:

- the existing read-only Sanchaya checkout;
- the canonical SQLite catalog;
- persistent release and Qdrant data;
- the Hugging Face model cache;
- the versioned ontology directory;
- OAuth state; and
- the allowlist file.

The serving processes must load the ontology snapshot that matches the selected
release. Both MCP services default `RETRIEVAL_ONTOLOGY_PATH` to the repository's
`ontology/jyotisha-v0.4.0.json`; for a different release, override it with the
matching mounted ontology snapshot when recreating both services. Do not change
the builder's ontology input as part of a runtime-only activation.

Secrets and the live allowlist remain outside Git.

## First complete build

```bash
make check
make build
make index
make inspect
make smoke
```

Equivalent one-command flow:

```bash
make pilot
```

`make index` first refreshes the canonical catalog, starts and waits for
Qdrant, then builds chunks, entity artifacts, vectors, and the release record.
It can be expensive because embedding work scales with selected chunks.

## Optional catalogue SQL

The [catalogue SQL PRD](catalog-sql-prd.md) defines the optional read-only
`query_catalog` tool and `retrieval://catalog-schema` resource. The tool is for
metadata aggregates; use `search_corpus` for passage search. Existing
tools/routes continue unchanged with it disabled.
After local security/regression tests pass, set `MCP_CATALOG_SQL_ENABLED=true`
in the operator-managed env file and rebuild/recreate the relevant MCP runtime
processes. The same flag is passed to bearer and OAuth services. Disabling the
flag and recreating the processes removes the capability.

This derives an in-memory projection from the existing hash-verified release
catalogue: do **not** run `make index`, `make catalog`, or a vector rebuild to
enable it. No release files are rewritten. Read-only local verification:

```bash
uv run python scripts/smoke_catalog_sql.py --release /absolute/path/to/active-release.json
```

For a configured bearer runtime, `scripts/mcp_smoke.py --catalog-sql` checks
discovery, reads the schema, and reconciles SQL coverage with `get_corpus_info`
in addition to its existing checks. OAuth uses the identical tool implementation;
an intended-client OAuth tool call is still required for end-to-end deployment
verification. Quotas are process-local; multiple replicas do not share counters.

## Start an existing release

When a compatible active release and Qdrant collection already exist:

```bash
make check
make up
make smoke
make search-smoke
```

`make up` builds the runtime image and starts bearer MCP, OAuth MCP, and the
local HTTPS adapter in development. Production uses its existing external
Caddy. It reuses release, Qdrant, model-cache, allowlist and OAuth-state data.
The target requires the existing OAuth environment to be configured.

For a separate HTTPS/OAuth edge check:

```bash
make oauth-config
make edge
make edge-smoke
```

`edge-smoke` verifies OAuth discovery and protected-route behavior. A complete
interactive login still requires an OAuth-capable client and an allowlisted
Google account.

## Update paths

### Incremental corpus/vector update

Use this for reviewed additions or edits. Unlike `make index`, it never deletes
or writes the serving collection. It copies compatible vectors into a separate
candidate, embeds only misses, rebuilds inexpensive chunk/entity/catalog
projections, and verifies the exact target point inventory before release.

```bash
make index-incremental                         # plan; no embedding or activation
make index-incremental APPLY=1                 # build/resume a staged candidate
make index-incremental APPLY=1 ACTIVATE=1      # verify and activate the candidate
```

The default plan builds the local builder image, but does not start Qdrant,
download models, or write corpus/release/vector data. It requires an existing
active release, running Qdrant and the model already in the shared model cache.
`APPLY=1` also refreshes the canonical catalog and starts/waits for Qdrant.
No command here restarts MCP, operates Zoekt, or changes the production host
from a development checkout. After an approved production activation, restart
both MCP services (`make up`) and run `make smoke`, `make search-smoke`, and
`make edge-smoke`. Refresh Zoekt separately to the same Sanchaya commit before
activation so lexical/retrieval provenance agrees.

Reuse keys cover the actual prefixed embedding text (including title and
headings), loaded weight hash, tokenizer hash, model revision, pooling/module
configuration, sequence length/truncation, normalization and library versions.
Changed model/configuration means cache misses, not silent reuse. Query-time
loading verifies the same identity for new fingerprinted releases.

The default guard allows at most 2,000 cache misses. A reviewed override is:

```bash
make index-incremental APPLY=1 INCREMENTAL_ARGS='--max-embed-chunks 2500'
```

**Legacy bootstrap:** old releases did not record exact weights/tokenizer
identity. Their plans show *provisional* reuse and
`legacy_attestation_required: true`; apply refuses to proceed. First verify
that the old build used the same cached weights and embedding settings, then
explicitly attest the fingerprint displayed by the plan:

```bash
make index-incremental APPLY=1 \
  INCREMENTAL_ARGS='--legacy-model-attestation <displayed-64-character-fingerprint>'
```

This is an operator attestation, not retrospective cryptographic proof. If the
old identity cannot be established, do not attest it: use a deliberate full
build instead. New releases retain exact configuration and input fingerprints,
so later reuse needs no attestation.

Build checkpoints live below `RETRIEVAL_BUILD_ROOT/incremental/<release-id>/`,
on the persistent build mount. Repeating the same command resumes by validating
acknowledged candidate points, including writes completed just before a crash.
Changed inputs, foreign collections, corrupt payloads, invalid vectors and
concurrent incremental builds fail closed. Completed staged releases can be
activated without recomputing embeddings; unchanged active inputs are a no-op.
Old releases/collections are retained for rollback; nothing is garbage-collected.

### Metadata-only change

```bash
make catalog
make mcp
make mcp-smoke
```

Rebuild projections as well if the metadata change affects source selection,
identity, or provenance referenced by chunks.

### Ontology-only entity candidate

When the corpus, chunks, catalog and vector collection are unchanged but the
ontology changes, build a standalone candidate from the exact base release:

```bash
uv run python scripts/build_retrieval_entity_release.py \
  --base-release /path/to/releases/active-release.json \
  --ontology ontology/jyotisha-v0.3.1.json \
  --output-root /tmp/patra-darpan-entity-candidate
```

The output root must be outside the configured release root. The builder
verifies every base artifact hash, retains catalog/chunks/vector provenance,
rebuilds only the ontology snapshot and entity projections, and loads the
result through the normal release and entity adapters. It never writes an
`active-release.json` pointer or the configured release root. By default this
is a file-level candidate check and does not contact Qdrant; add
`--qdrant-url http://127.0.0.1:6333` for a read-only audit of collection
dimensions, point IDs and chunk payload keys. Do not stage or activate a
candidate until the vector inventory has been audited and publication is
approved.

### Sanchaya revision with unchanged selected bytes

If a Sanchaya cleanup changes Git history or lexical/catalog provenance but a
read-only source-hash audit proves that every selected source byte is
unchanged, use the metadata-only release refresh:

```bash
make refresh-release
```

The builder verifies all selected source hashes, rewrites only the
`corpus_revision` fields in the entity projections, checks the existing
Qdrant collection's deterministic point IDs and payload keys, and assembles a
new release.  It does not run `make index`, does not call the vector builder,
and does not delete or recreate the collection.  The previous release remains
on disk for rollback.  To stage the release without switching the active
pointer, run the script directly with `--no-activate` and inspect the printed
release/work paths before rerunning with `--activate`.

This path is invalid when selected content, chunk boundaries, chunker
settings, embedding inputs, model, vector dimensions, or normalization have
changed; use the full corpus/index path below in those cases.

### Patra Darpan runtime or MCP code change

```bash
make check
make up
make smoke
make search-smoke
make edge-smoke
```

This path does not rebuild vectors. For a clean runtime restart after pulling
a reviewed commit:

```bash
git pull --ff-only
make down
make up
make smoke
make search-smoke
```

`down` is optional for a normal update: `up` rebuilds the runtime image and
Compose recreates changed services. Neither command removes persistent data.
No first-time setup, catalog build or index build is needed for the search
interface changes. `make build` remains the target for building both runtime
and builder images; `make runtime-build` builds only the online runtime.

Existing clients retain the same URL, OAuth configuration and tool names.
Additive tool options/resources appear when the client reconnects or refreshes
its tool list. Some hosts cache tools/instructions in existing conversations;
refresh or start a new conversation if new options are not visible. A runtime
restart alone does not require a new OAuth registration, though normal token
expiry may still require login.

### Corpus, chunking, ontology, entity, or embedding change

```bash
make check
make build
make index
make inspect
make smoke
make edge
make edge-smoke
```

### Sanchaya-Zoekt change

Deploy and verify that repository independently. The retrieval MCP expects:

- Docker network `sanchaya-zoekt_default`;
- service name `zoekt-webserver`;
- private URL `http://zoekt-webserver:6070`; and
- an index built from the Sanchaya revision recorded by the retrieval release.

## Production preparation

1. Push reviewed Patra Darpan and Sanchaya-Zoekt commits independently.
2. Pull each repository on the production host.
3. Confirm the Sanchaya-Zoekt UI and private RPC service are healthy.
4. Confirm the production env file contains correct host paths and OAuth
   credentials.
5. Run `make check` in Patra Darpan.
6. Choose the update path above; avoid `make index` for edge-only or MCP-only
   changes.
7. Inspect the active release and run backend, MCP, and edge smoke checks.

The production Qdrant, releases, model cache, OAuth state, and allowlist live on
persistent host storage. Do not remove Compose volumes or those paths during a
normal deployment.

## Verification

`make smoke` combines:

- `make backend-smoke`, which checks catalog, entity, passage, Zoekt, and
  Qdrant adapters; and
- `make mcp-smoke`, which initializes MCP and exercises representative tools.

`make search-smoke` verifies guide discovery, filename-only lexical search,
script expansion, bounded match continuation, passage paging and source links
through a real authenticated MCP session against the existing release.

`make edge-smoke` separately checks OAuth discovery and public route
protection. On production, also verify the Sanchaya UI returns `200` and public
`/api/*` remains blocked.

## Recovery principles

### F06 lexical runtime verification (no index rebuild)

The bounded-search change only affects MCP runtime code and its baked-in search
guide. It requires neither catalogue/vector release creation nor Zoekt reindexing.
Keep the existing release, collection and rollback image. Rollout remains an
explicit operator decision after candidate verification.

The adapter sends Zoekt `Opts.MaxWallTime=5000000000` (Go nanoseconds), leaving
headroom before the ten-second HTTP read timeout. This is a cooperative backend
work budget, not a hard end-to-end deadline. On the deployed Zoekt revision
`2cb19912a407`, a read-only three-second probe returned partial F06 hits in about
3.1 seconds, with `FilesSkipped` and `ShardsSkipped` nonzero but `FlushReason=0`.
Never infer completeness from `FlushReason` alone.

Verify the candidate against the existing backend with the original query:

```text
(धनिष्ठ|धनिष्ट|धनीष्ठ|dhaniṣṭ|dhanishta) -file:patra-darpan/papers
```

Use lexical mode, `result_type="files"`, `limit=1`. A complete answer or an
explicitly partial/failed answer is acceptable; an unlabelled empty success is
not. Check `lexical_query` includes both `-file:patra-darpan/catalog/` and
`-file:ontology/`, including on errors. For partial hits, follow a cursor and
confirm the final page still reports incompleteness. Retry the literal branches
joined by lowercase `or` with the same scope; uppercase `OR` is not equivalent.
Do not require a fixed count: the live lexical corpus can change independently.

`python scripts/smoke_lexical_limits.py` performs these candidate checks through
an in-process MCP client against live Zoekt, using the configured existing
release. Run it in an isolated runtime container with read-only release mounts;
it does not test HTTP authentication or interactive OAuth. It requires the
lowercase-`or` retry to return an exact, nonempty response, without pinning a count.

After approved runtime-only rollout, repeat these checks through both MCP
routes and run the existing search/SQL/auth smoke checks. Record serving image,
active release/catalogue hashes and unchanged Qdrant collection/point count.

- Inspect before rebuilding. `make inspect` and Qdrant collection information
  show whether expensive artifacts already exist.
- If embeddings completed but release assembly failed, repair and rerun release
  finalization rather than embedding again.
- Do not use `docker compose down -v` for normal operation.
- Do not delete Zoekt shards, Qdrant data, release directories, or model caches
  as generic cleanup.
- Review Docker disk usage before building images or embeddings on the
  production data disk.

## Stop and logs

```bash
make logs
make down
```

`make down` stops the Patra Darpan companion project. It does not manage the
separate Sanchaya-Zoekt project.
