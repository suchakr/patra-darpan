# Production retrieval deployment

This is the controlled deployment sequence for the retrieval companion on the
Sanchaya host. The retrieval containers are structurally deployable, but the
public endpoint is not ready until the Zoekt RPC flag, Caddy route, and
bearer-token boundary have been tested locally and pulled into both
production repositories.

## Preconditions

- Use the exact DNS name already present in the Sanchaya Caddyfile:
  `sanchaya.rasowshi.us`.
- The Sanchaya-Zoekt webserver must run with `-rpc`. Its RPC listener remains
  private; Caddy must deny public `/api` and `/api/*` paths.
- The retrieval and Sanchaya projects must share the external Docker network
  `sanchaya-zoekt_default`.
- The production Sanchaya checkout must be clean and contain the exported
  `patra-darpan/` Markdown tree. The builder rejects a dirty source checkout.
- The Patra Darpan checkout must contain the canonical SQLite catalog at the
  path supplied by `RETRIEVAL_CANONICAL_CATALOG`.
- The host-only env file must set `MCP_BEARER_TOKEN`. The pilot uses one shared
  trusted-demo token; do not commit it or place it in a URL.
- Keep enough disk for the E5 model cache, the Docker image, Qdrant storage,
  and one release build. The first CPU build is a long-running offline job.

Create the host-only env file from the checked-in
[production example](../../retrieval.env.prod.example) on first setup.
`make PROD=1 prod-env` copies it to `/etc/patra-darpan/retrieval.env`
without overwriting an existing file. Edit the host paths and replace the token
placeholder before continuing. The production overlay supplies
`QDRANT_URL=http://qdrant:6333`; do not point it at `host.docker.internal` or
publish port 6333.

## Deploy and build

Run the commands from the dedicated semantic checkout (for example,
`~/sg/patra-darpan`). Do not switch a separate Patra Darpan GUI checkout from
`main` to the semantic branch. The Makefile derives its repository path from
the checkout, so no `PD_DIR` or `ZO_DIR` variable is needed:

```bash
cd "$HOME/sg/patra-darpan"
make PROD=1 prod-env  # first-time setup; preserves an existing env file
```

1. Update the repositories and select the reviewed commits. The Sanchaya
   checkout used by the builder must be the same content revision used by
   Zoekt. Rebuild the Patra Darpan canonical catalog if its metadata changed.

2. Validate the production overlay before changing services:

   ```bash
   make PROD=1 check
   docker network inspect sanchaya-zoekt_default >/dev/null
   ```

3. Build the images from the reviewed Patra Darpan checkout:

   ```bash
   make PROD=1 build
   ```

4. Start private Qdrant. It has no host port in the production overlay:

   ```bash
   make PROD=1 qdrant
   ```

5. Run the one-shot release builder. This creates the manifest, chunks,
   entity JSONL, E5 vectors, release catalog, and active release. It does not
   start MCP and it does not change the Zoekt index.

   ```bash
   make PROD=1 index
   ```

   Re-running for the same active source revision is a no-op. A changed
   Sanchaya revision, ontology version, or build scope must produce a new
   release ID before activation.

6. Inspect the release before exposing it:

   ```bash
   make PROD=1 inspect
   ```

7. Start MCP on the private network. No MCP or Qdrant host ports are exposed:

   ```bash
   make PROD=1 mcp
   docker compose --env-file /etc/patra-darpan/retrieval.env \
     -f docker-compose.retrieval.yml \
     -f docker-compose.retrieval.prod.yml ps
   ```

8. The MCP route and `/api` denial are committed in the Sanchaya-Zoekt
   repository. Do not hand-edit them on the host. The MCP service validates
   the bearer token from the host-only env file. Reload Caddy using the
   existing Sanchaya-Zoekt procedure, then test the public URL with an MCP
   client:

   ```text
   https://sanchaya.rasowshi.us/mcp
   ```

   Send `Authorization: Bearer <MCP_BEARER_TOKEN>`. Requests without the
   token receive `401`; the public Zoekt UI remains available.

## Subsequent corpus or code updates

- Sanchaya content update: update the Sanchaya checkout, rebuild Zoekt using
  its normal indexer workflow, run the retrieval builder, inspect the new
  release, then restart MCP if activation changed.
- Retrieval code or ontology update: update the Patra Darpan checkout, rebuild
  the images, run the builder, inspect the new release, then restart MCP.
- Keep the previous release directory and Qdrant collection until the new
  public smoke test passes; rollback is changing the active release pointer
  and restarting MCP.

The online MCP service is read-only. Index creation and release activation are
explicit offline operations so a service restart cannot trigger a long
embedding job.
