# Sanchaya Retrieval: client search guide

Use `get_corpus_info` to inspect the active release and its coverage. Read this
guide once per conversation; resources need not be reread before every call.

## Choose the index and tool

- **Catalog:** `get_author_works`, `search_documents` and batch metadata lookup
  answer document metadata questions. The full catalogue exceeds content coverage.
  When `query_catalog` is advertised, read `retrieval://catalog-schema` and use
  grouped SQL for catalogue-wide author/year/coverage aggregates; do not
  aggregate the first 50 `search_documents` results. Use `search_corpus` for
  passage search, not `query_catalog`.
- **Lexical:** `search_corpus(mode="lexical")` searches the Zoekt-indexed
  Sanchaya corpus, including files outside the release's chunk scope. Its
  `lexical_revision` is independent of the release `corpus_revision`; when
  results are returned, it is observed from Zoekt and any mismatch with the
  release-declared revision appears in `warnings`.
- **Vector:** `mode="vector"` searches the release's named Qdrant collection
  with multilingual E5. Its Sanskrit/paper scope is smaller than the lexical
  corpus. Semantic similarity is not an exhaustive occurrence inventory.
- **Hybrid:** the default merges ranked lexical and vector results. It is a
  top-k view. Use lexical mode for match counts and continuation.
- **Entities:** `lookup_entity` resolves explicit ontology aliases and returns
  bounded attributes, labelled incoming/outgoing relations and curation references.
  Under v0.4, item-level `status` on `attributes.contextual_synonyms` and
  `attributes.variant_evidence` is `provisional` or `approved`; provisional is
  not expert approval and is distinct from the result's registry status.
  `lookup_entity`, `list_entity_mentions`, `get_corpus_info`, and
  `retrieval://ontology-context` disclose `mention_assessment` counts: total,
  flagged, unflagged, and unassessed. Flagged forms are explicitly listed in
  `attributes.ambiguous_aliases`; unflagged means only “not on that finite
  list,” not contextually verified. Older mention rows without the flag are
  unassessed. `list_entity_mentions` pages known mentions in the entity projection.
  `entity_ids` filters search to known entity documents/chunks; it does not
  expand aliases or guarantee mentions beyond that subset.
- **Passages:** only documents with release chunks can be fetched. Check
  `fetch_available`. An unavailable fetch does not mean the text lacks a match.

## Catalogue aggregates (when enabled)

`query_catalog(query, max_rows=500)` queries `documents_v`, `authors_v`,
`subjects_v` and `coverage_v`. It is read-only and limited to catalogue metadata
aggregates; it cannot search passages. Use `search_corpus` for passage search.
The resource `retrieval://catalog-schema` describes the tool, view columns,
counted data issues, restrictions, and examples. These additions are absent
when the operator has not enabled catalogue SQL.

For example, “Which authors have the most works, and how many have full text?”:

```sql
SELECT a.author_id, a.author_norm,
       COUNT(DISTINCT a.document_id) AS catalogued,
       COUNT(DISTINCT CASE WHEN d.indexed_in_release = 1 THEN a.document_id END) AS full_text
FROM authors_v a JOIN documents_v d USING (document_id)
WHERE a.author_id IS NOT NULL AND d.source_kind = 'patra-darpan'
GROUP BY a.author_id, a.author_norm
ORDER BY catalogued DESC, a.author_id
LIMIT 20
```

Report the SQL and catalogue revision with an aggregate answer. Do not call all
catalogue records papers: acquisition provenance does not classify scholarly
document type. Author IDs normalize names, not fully disambiguated people;
disclose unreviewed/ambiguous and missing names. Include unknown years in decade
totals, and report untagged documents before interpreting subject counts.

Inspect `truncated` and `truncation_reason`; `row_count` is returned rows, not
the total number of matches. Row/byte-limited results are not complete lists.
Use deterministic ORDER BY and keyset predicates for further pages. One SELECT
with optional WITH is accepted, but only listed views and safe functions are
allowed. SQL cannot fetch document content or access the filesystem.

## Explore ontology knowledge

Read `retrieval://ontology-context` once to discover entity vocabulary and the
`knowledge_lookup` pointer. Use `lookup_entity(name=..., limit=1)` for knowledge
about a resolved entity. It includes the active ontology ID/version, attributes,
curation status and relations with related entity IDs and preferred labels.
For outgoing relations the queried entity is the source; for incoming relations
it is the destination. Follow `target_preferred_label` with another lookup.
For example, follow a person's incoming `authored_by` link to the work before
reading that work's `composed_at` relation; do not treat a work's location as
the person's birthplace or a general biographical fact.

These are curated/pilot ontology assertions, not new facts extracted from the
current corpus. `source_ref` describes entity curation, not an edge-level
citation. Use `list_entity_mentions` and fetched passages to seek evidence.
Check `attributes_truncated`, `relations_truncated`, `knowledge_truncated`,
and `results_truncated`; limits can omit knowledge or results. A false
`relation_projection_consistent` means the node-local projection is stale;
the canonical relation table is used.

## Zoekt queries and filename-only results

The lexical query accepts Zoekt's query language. Terms separated by spaces
are ANDed at file scope, so they need not occur on the same line. Parentheses,
lowercase `or`, regex alternatives, exclusions and qualifiers can express exploration.
Uppercase `OR` is not an equivalent Boolean operator on the deployed parser.
Use `\s` for whitespace inside a regex; ordinary query spaces separate terms.

| Question | `search_corpus` arguments |
| --- | --- |
| Which Jyotiṣa files contain सूर्य? | `query="file:Jyo type:filename सूर्य", mode="lexical"` |
| Same question with structured options | `query="सूर्य", file_filter="Jyo", result_type="files"` |
| References in either script | `query="(श्रविष्ठा|Śraviṣṭhā)", mode="lexical"` |
| Literal alternatives when a broad regex is slow | `query="(धनिष्ठ or धनिष्ट or धनीष्ठ or dhaniṣṭ or dhanishta) -file:patra-darpan/papers", mode="lexical", result_type="files"` |
| Purāṇa occurrences excluding one path | `query="सूर्य file:Puranani -file:gretil", mode="lexical"` |
| Case-sensitive IAST | `query="case:yes Śraviṣṭhā", mode="lexical"` |
| A specific textual sequence | `query="सूर्य\s+चन्द्र", mode="lexical"` |

`type:filename` controls the returned result: filenames of matching files,
without content. To match the filename itself, use `file:`. Filename-only
requests use lexical search even if the caller leaves the default hybrid mode.
Catalog and ontology paths are excluded by the adapter. Returned
`lexical_query` records the actual expression sent to Zoekt.
Literal alternatives joined by lowercase `or` can be faster than a broad regex
alternation. This is a user-selected retry, not a general regex rewrite: retain
the same scope and semantics. The server never silently rewrites raw regexes.

## Script expansion

For **plain Sanskrit terms**, request `script_expansion="devanagari"`,
`"iast"` or `"harvard_kyoto"` according to the input. The server generates
equivalent Devanāgarī, IAST and Harvard–Kyoto alternatives and reports them
in `query_forms`. Multiple terms remain ANDed.

Example: `query="सूर्य", script_expansion="devanagari", file_filter="Jyo"`.
`auto` recognizes Devanāgarī and IAST diacritics; ASCII remains unchanged
because English, IAST and Harvard–Kyoto can be ambiguous. Specify the scheme
for ASCII Sanskrit. Harvard–Kyoto is case-sensitive as a writing system.

Expansion does not rewrite operators, regex or qualifiers. Put path scope in
`file_filter`, or submit a complete raw query with `script_expansion="none"`.
The vector backend receives the original question; lexical syntax is not an
appropriate semantic question. Prefer separate calls when composing complex
Zoekt expressions. Transliteration does not generate spelling corrections,
declensions, synonyms, or the Lab's final-a-removal heuristic.

## Bounded responses and complete exploration

Lexical responses default to 400-character windows and no surrounding lines.
`snippet_chars` allows 80–1600 characters; `context_lines` allows 0–3.
`limit` bounds files per page; `match_limit` bounds match windows per page.
Byte limits may make a page smaller than requested.

The adapter supplies a five-second Zoekt search-work budget (`MaxWallTime`).
Its ten-second HTTP read timeout is an inactivity backstop, not a guaranteed
end-to-end deadline. `limit=1` reduces displayed rows, not backend search work.
Budget-limited responses retain any returned hits and set `search_incomplete=true`
and `lexical_stats.status="partial"`. Check skipped files/shards, cancellation,
display/snapshot limits and `counts_exact` before using totals.

If no usable response arrives, `lexical_error` supplies a safe code, message and
retry hint; `lexical_stats.status="failed"`, backend counts are `null` (unknown),
and `search_incomplete=true`. Existing `backend_errors.lexical` remains available.
An empty failed/partial response is **not** evidence of no matches. Narrow with
`file_filter`, retry literal alternatives with lowercase `or`, or run separate
queries. Do not sum separate-query file counts without deduplicating overlaps.
In hybrid mode these flags describe the lexical branch; vector results can
still be returned. Vector-only responses leave lexical status fields `null`.

For lexical continuation, repeat the same query, expansion, file filter,
entity IDs, snippet size and context with `next_cursor`. Cursors refer to a
bounded in-memory snapshot, expire after five minutes, and are lost on a
server restart or cache eviction. Restart the search if a cursor expires.
Continuation pages drain the retained snapshot; they do not resume backend work.
Even the last page (`has_more=false`) remains incomplete if that snapshot was
partial. A complete empty response has `counts_exact=true` and no lexical error.

`backend_counts` counts adapter candidate rows before fusion, not total occurrences. `lexical_stats`
reports backend file/match counts, whether evidence accounts for those counts,
and backend/snapshot limits. `counts_exact=false` means the figures are
backend-reported counts without a completeness guarantee. Counts refer to
indexed files/editions, not deduplicated works. Finish all pages and check
limits before claiming an exhaustive inventory. Narrow the file scope when
the bounded snapshot or backend response is limited.

For documents, `fetch_passage(offset=..., limit=...)` returns `total_passages`,
`has_more` and `next_offset`. Follow `next_offset` to move beyond the first
20 chunks. For shortened chunk text, fetch the returned `chunk_id` with
`text_offset=next_text_offset`; `max_chars` controls the text window.
`fetch_passages` accepts these same fields per item. If its byte budget is
reached, resend the unprocessed requests from `next_request_index`.

## Sanskrit exploration with the LLM

1. Start with the supplied form and the appropriate script equivalents.
2. Propose plausible declensions and compare their passages. Case endings can
   change the surface form; a stem search can also match unrelated words.
3. Try joined and separated forms for sandhi, and distinctive components as
   well as the whole samāsa. Components alone do not prove the full expression.
4. Treat reconstructed forms and deity-based names as hypotheses. Check their
   sense in context before equating them with a canonical entity.
5. Record the forms and scopes tried. A search failure is not evidence of
   absence, especially with partial coverage, OCR, limits or variant editions.

## Answers and links

Use readable Markdown hyperlinks: **[work or paper title](citation_url)**,
followed by a verse, section or line when available. Prefer `citation_url`
for a supplied original-paper source and `source_url` for the indexed text.
IDs are retrieval handles; they should not dominate the reader's answer.
Use only returned URLs or catalog source references, and do not invent titles,
verse anchors or claims of original-edition authority. GitHub text links are
pinned to the result revision; paper links may point to a PDF.

Authoritative syntax reference: [Zoekt query parser](https://github.com/sourcegraph/zoekt/blob/main/query/parse.go).
