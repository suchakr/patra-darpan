# F06 runtime fix: implementation and candidate verification

Date: 24 October 2026. Input: agent-handoffs batch 008, F06. Implementation
approved by Sundar's subsequent “Proceed”; production rollout remains gated.

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

## Deployment state and remaining work

No commit, push or deployment performed. Serving bearer and OAuth container
IDs, image IDs and start times were identical before and after verification.
The serving image remains
`sha256:76378aee5cd524fdfb80fa111368b0bd6e5695127a107fceb400ff95f53cb753`.

Unchanged active release: `retrieval-jyotisham-all-080b5f6-inc-722eba369e`.
Catalogue revision:
`c48048a49f536b8d1a8d893b0244a9e7c3102feed54d8388b2b8e51b86156e73`.
Active release file SHA-256:
`81ba105f0df7f7e448bd686f720b5f8f533c3842874ec3b6648c8cd69843cbb7`.

Next, with separate approval: commit only F06 files, push, perform a runtime-only
rollout, and repeat authenticated search/SQL/edge smoke checks on both routes.
Retain the earlier release and rollback image. No catalogue, vectors, source
corpus or Zoekt index needs rebuilding. Planner-level regex optimization is
deferred; F06 is mitigated with bounded partial results and a verified retry.
