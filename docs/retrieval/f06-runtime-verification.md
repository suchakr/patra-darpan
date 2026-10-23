# F06 lexical mitigation: verification and rollout

Date: 24 October 2026. Input: agent-handoffs batch 008, F06. Implementation
approved by Sundar's subsequent “Proceed”. Production rollout was separately
approved after Sundar accepted mitigation; see the final section below.

## Disposition and diagnosis

Accepted: bounded lexical searches, safe and actionable errors, correct query
echoes, regression tests and client guidance. No automatic regex rewriting,
longer HTTP timeout, catalogue/vector rebuild, ontology change or Zoekt upgrade.

The protected catalogue/ontology exclusions were already sent to Zoekt. The
missing suffix on failures was a response-reporting defect, not a different
query construction path. The mixed-script regex remains slow on the deployed
Zoekt revision `2cb19912a407`; the exact planner-level cause is not established.
Lowercase Boolean `or` is a verified fast retry for these literal alternatives.
Uppercase `OR` is not equivalent on this parser and must not be recommended.

## Implementation

- Send a five-second backend work budget, retaining the ten-second HTTP read
  backstop. This is cooperative cancellation, not a hard RPC deadline.
- Keep any partial hits, expose `search_incomplete` and lexical status, and
  preserve incompleteness across cached continuation pages.
- Report unknown backend counts on failed requests, with safe structured errors
  and retry guidance; retain existing `backend_errors` for compatibility.
- Echo the protected effective query on transport/backend failures as well as
  success. Keep raw expressions and the vector query unchanged.
- Correct MCP tool description, search guide and corpus-info guidance; add
  `scripts/smoke_lexical_limits.py` for repeatable candidate checks.

## Verification

Local clean candidate snapshot: 110 tests ran, 109 passed, one optional Torch
test skipped because that isolated Python environment lacks Torch. Production's
Linux runtime image: all 109 selected tests passed, including the Torch test;
only the Makefile dry-run test was excluded because the runtime image lacks
`make`. That dry-run test passed locally. Fourteen new F06 tests cover transport
and streamed timeouts, partial snapshots, empty results, unsafe error details,
raw syntax preservation, hybrid/vector behaviour, response bounds and real
in-process MCP serialization/tool discovery.

A disposable read-only container used the existing production image with the
candidate source mounted read-only, the existing release mounted read-only, and
the live Zoekt API. No image build, service restart or index writes occurred.
Through a real in-process MCP client:

- Original regex: 5.529 s elapsed, 57 backend files/matches, one displayed file,
  `status=partial`, `counts_exact=false`, 466 skipped files and one skipped shard.
  Continuation preserved the same incomplete stats. `FlushReason=0` alone did
  not establish completeness.
- Lowercase-`or` retry with identical scope: 0.018 s elapsed, 120 backend
  files/matches, `status=complete`, `counts_exact=true`, no skipped work.

Counts and timings are dated observations, not future acceptance constants.
This checked candidate MCP serialization, not production HTTP authentication
or an interactive OAuth login. SQL/auth regression tests passed; the production
routes were not replaced or restarted.

## Pre-deployment snapshot

At candidate verification, no commit, push or deployment had been performed.
Serving bearer and OAuth container
IDs, image IDs and start times were identical before and after verification.
The serving image at that point was
`sha256:76378aee5cd524fdfb80fa111368b0bd6e5695127a107fceb400ff95f53cb753`.

Unchanged active release: `retrieval-jyotisham-all-080b5f6-inc-722eba369e`.
Catalogue revision:
`c48048a49f536b8d1a8d893b0244a9e7c3102feed54d8388b2b8e51b86156e73`.
Active release file SHA-256:
`81ba105f0df7f7e448bd686f720b5f8f533c3842874ec3b6648c8cd69843cbb7`.

Planner-level regex optimization is deferred; F06 is mitigated with bounded
partial results and a verified retry, not made intrinsically fast.

## Approved production rollout — 2026-10-24

- Runtime code commit: `89477b2b2e027bae797bd0e1535cf425514d9cf4`, pushed to main
  and fast-forwarded on production. Only the seven reviewed F06 files were
  committed; unrelated local Decode Lab changes remain untouched.
- New serving image:
  `sha256:fb1ac99cce7d045a3be49146c5cbe8c6c6c00b18d48b9822656f23e013d0b55c`.
  Cached dependency layers were reused; only MCP application layers changed.
  Candidate also retained as `patra-darpan-retrieval-mcp:f06-89477b2`.
- Local pre-commit retrieval/auth/release suite: all 110 tests passed. Newly
  built production image: all 109 selected Linux tests passed; the Makefile
  dry-run was excluded because the runtime image lacks `make`. Its schema
  fixture was mounted read-only for the image tests; no fixture or test code
  was added to the serving image.
- Before activation, the new image passed live F06 and catalogue SQL checks
  against existing read-only release mounts. Coverage reconciled to 2,024
  Patra Darpaṇa records / 150 indexed and 34 Sanchaya texts / 34 indexed.
- Only bearer/OAuth MCP services were recreated, using `--no-deps --no-build
  --pull never`. Qdrant, Zoekt and Caddy container IDs, images and start times
  were unchanged. No environment configuration was edited.
- Serving backend/vector, entity, passage, metadata, search-feature, bearer SQL
  protocol and public auth/edge checks passed. Sanchaya UI returned 200;
  public `/api/search` remained blocked (404). Unauthenticated requests to both
  MCP routes returned 401.
- Authenticated public bearer F06: original regex returned 50 backend files
  as explicitly partial results in 5.105 s; lowercase-`or` returned an exact
  120 in 0.024 s. Cached continuation retained the same completeness metadata.
- The existing authenticated Sanchaya client also called `get_corpus_info`,
  both F06 queries, `retrieval://catalog-schema` and `run_sql` successfully.
  Its OAuth regex result was explicitly partial (30 backend files, backend
  duration 5.041 s, client-call elapsed 7.857 s). Lowercase-`or` returned an
  exact 120 (backend 0.015 s, client-call elapsed 1.908 s). This verifies the
  intended client, not just discovery/401 reachability; no fresh Google login
  was performed. Counts/timings vary with scheduling and transport overhead.
- Active release, every hash-verified file artifact and the catalogue revision
  above remained unchanged. Qdrant remains green at
  `sanchaya-inc-080b5f66-722eba369ec06f84`, 7,826 points. No catalogue/release
  build, corpus re-embedding, Zoekt reindex, corpus publication, paid provider
  calls or model downloads occurred. Vector smoke used the existing cached
  query-embedding model. `/mnt` remains 90% used, approximately 1.6 GiB free.

### Rollback retained

The immediately previous serving image is tagged
`patra-darpan-retrieval-mcp:pre-f06-89477b2`. The older pre-catalogue-SQL rollback
image/release were also preserved. No rollback was needed.

To restore the prior MCP application while preserving current configuration
and all existing indexes, on production:

```bash
cd /home/kumars/sg/patra-darpan
sudo docker image tag patra-darpan-retrieval-mcp:pre-f06-89477b2 \
  patra-darpan-retrieval-mcp:dev
sudo docker compose \
  --env-file /etc/patra-darpan/retrieval.env \
  -f docker-compose.retrieval.yml \
  -f docker-compose.retrieval.prod.yml \
  --profile runtime --profile oauth \
  up -d --no-deps --no-build --pull never --force-recreate \
  retrieval-mcp retrieval-mcp-oauth
```

Then repeat backend/protocol/auth smoke checks. A rollback retains the original
slow-query behaviour; it does not optimize the regex. This record-only update
does not require another image build or service restart.
