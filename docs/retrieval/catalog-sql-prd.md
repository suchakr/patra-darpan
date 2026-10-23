# Catalogue SQL access — PRD and implementation contract

Status: implemented locally; production enablement is a separate operator action.

## Purpose

Allow Sañcaya / Patra Darpaṇa MCP clients to answer ad-hoc metadata aggregates
without enumerating the existing 50-result metadata search. Reuse the immutable,
hash-verified retrieval catalogue derived from canonical Patra Darpaṇa SQLite
and the Sanchaya release manifest. Do not expose the live canonical database,
accept client filesystem paths, or change existing metadata/search tools.

The chosen approach is curated SQL views rather than a growing set of typed
aggregate tools. A typed summary would suffice for a dashboard, but SQL supports
the recurring exploratory questions that motivated this work.

## Added MCP surface

- `retrieval://catalog-schema`: JSON schema, view columns/types, revisions,
  normalization rules, known issues with counts, and executable examples.
- `run_sql(query, max_rows=500)`: one read query over the approved views.
- Both are absent unless `MCP_CATALOG_SQL_ENABLED=true`. This gate applies to
  OAuth, bearer, and local transports; existing tools/routes remain available.
- No additional `list_authors` tool in this iteration.

| View | Purpose |
| --- | --- |
| `documents_v` | One row per catalogue record, including normalized/raw year, provenance, coverage, PDF URI and conservative document type |
| `authors_v` | One row per extracted author occurrence: identity, display name, original string, extracted name, position, resolution status |
| `subjects_v` | Existing document subject tags and their provenance; not inferred subject classification |
| `coverage_v` | Document counts grouped by source kind, source collection and indexed status |

`source_kind` means `patra-darpan` versus `sanchaya`. `source_collection`
distinguishes IJHS, curated PDFs, curated links, mixed provenance and unknown.
Acquisition channel is not document type. Patra Darpaṇa record types remain
`unknown` unless an authoritative classification is supplied in a future version;
Sanchaya manifest texts are `source_text`. Do not call all records papers. A
`papers_v` is deliberately deferred until paper classification is trustworthy.

At source revision `080b5f6`, the historical acceptance baseline is 2,024 Patra
Darpaṇa records, 34 Sanchaya texts, 184 indexed records, of which 150 belong to
Patra Darpaṇa. These are snapshot assertions, not constants in production code.
`indexed_in_release` describes passage/vector coverage in this release; it does
not establish coverage of the independently operated, broader Zoekt index.

## Data treatment and provenance

- Normalize four-digit integer years and integral decimal spellings (`2007.0`)
  to INTEGER; missing, ranges, malformed and non-four-digit years become NULL.
  Preserve `year_raw`; retain the unknown-year bucket in totals.
- Split explicit `and`, `&`, semicolon and middle-dot author separators, with
  conservative exceptions for institutional/collective names. Split comma lists
  only when each component has an unambiguous initials-plus-name shape (or is a
  single uppercase initial). Flag ambiguous surname-first strings and `et al.`.
- Preserve diacritics and source strings. Apply punctuation/spacing normalization
  and an explicit versioned alias table, never fuzzy person matching. The initial
  alias group joins S Mahdihassan / S Mahadihassan, evidenced by author fields and
  reciprocal PDF filename spellings in `corpus/ijhs.tsv` (IJHS 19, 1984 issue 1;
  IJHS 26, 1991 issues 1–2). Alias decisions are reviewable code, not runtime SQL.
- Non-reviewed identities are labelled `unreviewed`; ambiguous entries have NULL
  normalized identity/name. Missing authors produce no author row. Schema issues
  count these states. Known publisher/journal labels such as `IJHS` and `INSA`
  in author fields are flagged, not ranked as normalized people. Stable IDs are
  catalogue name identities, not assertions
  that homonyms denote one person. One co-authored document counts once per
  author; use `COUNT(DISTINCT document_id)` and do not sum author counts as a
  document total.
- Existing subject tags are incomplete, often release-manifest tags. Expose the
  untagged count; do not infer catalogue-wide subject prevalence from tagged rows.
- Every result includes submitted SQL, `catalog_revision`, `corpus_revision`,
  `release_id`, `schema_version`, `normalization_version`, and `analytics_revision`.
  The latter hashes the exact public projection and normalization configuration.
  The catalogue hash stays the hash of the unmodified release artifact.
  Authentication failures do not expose catalogue metadata; malformed/oversized
  SQL is not echoed or logged. The input limit also accounts for JSON escaping.

## Query and operational boundary

- Execute against a fresh, private in-memory projection in a spawned worker.
  Worker arguments contain public data only, not a release/database path or
  credentials. This is SQL capability restriction, not an OS filesystem sandbox;
  workers still inherit the ordinary process environment. No SQL function exposes
  that environment or host files.
- Single SELECT, optionally introduced by WITH; no EXPLAIN, DDL, DML, transaction,
  ATTACH/DETACH, PRAGMA (including table-valued forms), extension loading or host
  file functions. Use SQLite's single-statement execution and default-deny
  authorizer, permitting base reads only through approved views.
  A separate identifier check prevents CTE names from spoofing the authorizer's
  view provenance and handles quoted identifiers and COUNT(*) optimizations.
- Read-only/query-only connection, extensions explicitly disabled, trusted schema
  disabled, defensive mode where supported. Bound SQLite heap to 64 MiB, SQL to
  8,192 UTF-8 bytes, cells to 64,000 bytes, output columns to 32, expression depth
  to 30, compound queries to 5, and prepared VM instructions to 100,000.
- Hard worker deadline of five seconds including startup, projection, preparation,
  execution and result production. Progress interruption plus parent termination;
  terminate/reap unfinished workers on every exit path. A timeout returns an error,
  not partial aggregate results. SQL does not block the MCP event loop.
- Default 500 rows; explicit maximum 1,000. Fetch incrementally with an extra row
  to detect row truncation. Apply the byte budget to the complete MCP tool result
  (text + structured content), reserving transport overhead below 64,000 bytes.
  Preserve whole rows; return `truncated` and `truncation_reason`. `row_count` means
  returned rows, not total matching rows. Results require explicit ORDER BY for
  reproducible enumeration; larger lists use SQL keyset pagination.
- Per process: two concurrent workers, 12 attempts/minute per authenticated token,
  and 60 attempts/minute globally. Reject excess work without queuing. Quotas are
  per MCP process, not distributed across replicas or OAuth/bearer processes.
- Log bounded JSON containing SQL, a process-salted HMAC token ID, outcome,
  elapsed time and returned row count only. Never log bearer/access credentials,
  email addresses or result values. OAuth identity comes from the SDK's verified
  authentication context; bearer identity is set only after credential validation.
  Explicit local unauthenticated tests share one `local` quota. SQL logs can
  contain literals supplied by the client; clients must not put secrets in SQL.

One call answers aggregates whose result fits the limits. “List every author in
one call” is not guaranteed for arbitrarily large catalogues. No SQL truncation
may be presented by the client as a complete distribution.

## Acceptance and verification

1. One grouped query returns normalized author names and distinct document counts.
2. Year groups, including unknown, sum to the complete Patra Darpaṇa record count.
3. Directly count indexed Patra Darpaṇa records, without subtracting assumed text
   counts. The `080b5f6` fixture yields 150; catalogue total is 2,058.
4. The explicit Mahdihassan aliases form one identity; ambiguous authors remain
   flagged. Diacritics, co-author order, surname-first and institutional names
   survive round trips.
5. Reject writes, ATTACH, extension/file functions, raw tables (including
   COUNT(*)), sqlite_schema, table-valued pragmas and multiple statements.
   Accept SELECT, CTEs, aggregates, joins, comments and semicolons inside literals.
6. An expensive aggregate cross join / recursive query times out without leaving
   a worker alive; the next ordinary query succeeds. A row cap is not a CPU cap.
7. Test row/Unicode byte limits, invalid limits, oversized SQL/cells, revisions,
   rate limits, concurrency, identity isolation and log credential non-disclosure.
8. MCP discovery shows exactly one added tool/resource only when enabled. Test
   tool calls and schema reads using the SDK and authentication-context tests.
9. Existing retrieval/catalogue/auth tests remain green. No provider/model calls,
   production restarts or paid requests are part of verification.

## Rollout / rollback

Rebuild and recreate MCP runtime images using the existing release mounts. First
exercise the capability locally, then opt in with `MCP_CATALOG_SQL_ENABLED=true`
on approved deployments. Disable the flag and recreate those processes to roll
back. No canonical catalogue changes, release rewriting, corpus publication,
Zoekt reindexing, vector rebuilds or embedding/model downloads are required.
The SQL schema/normalization version and analytics hash change when its projection
rules change, even if the original catalogue and corpus revisions are unchanged.

Non-goals: automatic scholarly document classification, exhaustive author
disambiguation, lemma-aware retrieval, ontology relations, new deep links,
database download access, and changes to the existing search tool contracts.

## Local verification record — 2026-10-23

- 20 new catalogue SQL tests cover aggregates, author/year normalization,
  historical synthetic coverage, malicious queries, deadline cleanup, quotas,
  wire limits, SDK discovery, OAuth/bearer identity context and a real in-memory
  MCP client/server session.
- Combined retrieval, bearer-auth and release-refresh regression suite: 95 tests,
  including optional Qdrant-client tests using temporary/in-memory fixture data.
- Real read-only smoke: local release `retrieval-jyotisham-all-c6d35eb`, catalogue
  `6c67b2236f2fa551f0a00ae1396f796ed76f5f752dbf1fcb3c999bfb3d345390`.
  Counts: 2,024 Patra Darpaṇa records (120 indexed), 34 Sanchaya texts (34 indexed).
  Decade groups reconcile to 2,024; Mahdihassan alias group contains 18 distinct
  records. This older snapshot is **not** production `080b5f6` coverage evidence.
- Compose production overlay validates with the SQL flag passed to both MCP
  services and no additional published ports. Python compilation and diff
  whitespace checks pass.
- Existing source databases, saved releases and live indexes were not modified. No production deployment,
  interactive Google login, model download, paid call, commit or push was performed.

### Linux rollout preflight compatibility correction

The initial feature was committed as `7de544b`. Before replacing either serving
container, the new image's SQL tests were run on the production Linux runtime.
SQLite 3.46.1 reported an optimized view COUNT(*) base-read callback with both
database and view provenance NULL; macOS SQLite 3.50.4 supplied database `main`.
The default-deny authorizer therefore rejected legitimate counts on Linux.

The correction accepts only that specific column-less private-table read for
NULL/`main` database, still behind the independent private-identifier gate.
Ordinary raw-column reads, schema reads, other databases and direct private-table
SQL remain denied. A regression explicitly exercises both callback variants and
the private-table/CTE spoofing rejection. The SQL suite now has 21 tests. Linux
image tests and production-catalogue reconciliation must pass before enablement;
macOS-only verification is insufficient for this SQL authorization boundary.
