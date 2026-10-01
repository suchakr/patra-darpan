# Sanchaya Retrieval: client search guide

Use `get_corpus_info` to inspect the active release and its coverage. Read this
guide once per conversation; resources need not be reread before every call.

## Choose the index and tool

- **Catalog:** `get_author_works`, `search_documents` and batch metadata lookup
  answer paper metadata questions. The full paper catalog exceeds content coverage.
- **Lexical:** `search_corpus(mode="lexical")` searches the Zoekt-indexed
  Sanchaya corpus, including files outside the release's chunk scope.
- **Vector:** `mode="vector"` searches the release's named Qdrant collection
  with multilingual E5. Its Sanskrit/paper scope is smaller than the lexical
  corpus. Semantic similarity is not an exhaustive occurrence inventory.
- **Hybrid:** the default merges ranked lexical and vector results. It is a
  top-k view. Use lexical mode for match counts and continuation.
- **Entities:** `lookup_entity` resolves explicit ontology aliases and returns
  bounded attributes, labelled incoming/outgoing relations and curation references.
  `list_entity_mentions` pages known mentions in the entity projection.
  `entity_ids` filters search to known entity documents/chunks; it does not
  expand aliases or guarantee mentions beyond that subset.
- **Passages:** only documents with release chunks can be fetched. Check
  `fetch_available`. An unavailable fetch does not mean the text lacks a match.

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
the canonical relation table is used. Ontology v0.4 remains deferred.

## Zoekt queries and filename-only results

The lexical query accepts Zoekt's query language. Terms separated by spaces
are ANDed at file scope, so they need not occur on the same line. Parentheses,
`OR`, regex alternatives, exclusions and qualifiers can express exploration.
Use `\s` for whitespace inside a regex; ordinary query spaces separate terms.

| Question | `search_corpus` arguments |
| --- | --- |
| Which Jyotiṣa files contain सूर्य? | `query="file:Jyo type:filename सूर्य", mode="lexical"` |
| Same question with structured options | `query="सूर्य", file_filter="Jyo", result_type="files"` |
| References in either script | `query="(श्रविष्ठा|Śraviṣṭhā)", mode="lexical"` |
| Purāṇa occurrences excluding one path | `query="सूर्य file:Puranani -file:gretil", mode="lexical"` |
| Case-sensitive IAST | `query="case:yes Śraviṣṭhā", mode="lexical"` |
| A specific textual sequence | `query="सूर्य\s+चन्द्र", mode="lexical"` |

`type:filename` controls the returned result: filenames of matching files,
without content. To match the filename itself, use `file:`. Filename-only
requests use lexical search even if the caller leaves the default hybrid mode.
Catalog and ontology paths are excluded by the adapter. Returned
`lexical_query` records the actual expression sent to Zoekt.

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

For lexical continuation, repeat the same query, expansion, file filter,
entity IDs, snippet size and context with `next_cursor`. Cursors refer to a
bounded in-memory snapshot, expire after five minutes, and are lost on a
server restart or cache eviction. Restart the search if a cursor expires.

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
