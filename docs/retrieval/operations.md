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

### Metadata-only change

```bash
make catalog
make mcp
make mcp-smoke
```

Rebuild projections as well if the metadata change affects source selection,
identity, or provenance referenced by chunks.

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
