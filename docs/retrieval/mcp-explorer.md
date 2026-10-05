# Sanchaya MCP Explorer

## Purpose and boundary

`web/mcp-explorer.html` is a separate static SPA in the Patra Darpan main web
app, linked as **Sanchaya MCP**. It helps users understand retrieval, connect
an assistant and explore the curated ontology. It shares no application state
with the paper browser and requires no MCP containers or authentication to view.

Four URL-addressable sections: **Overview**, **Explore ontology**, **Connect
and try**, and **Coverage and limits**. The connection section gives the
preferred OAuth URL, explains allowlisted access and offers copyable prompts.
Coverage is a dated configuration summary, not a live release inventory. Users
must ask `get_corpus_info` for actual deployed scope/counts. No live health badge,
embedded chat, mention counts, editing or allowlist administration is included.

## Data and provenance

`ops/export_mcp_explorer.py` generates `web/assets/data/mcp-ontology.json` from
`ontology/jyotisha-v0.3.json`. It validates unique IDs and relation endpoints,
retains attributes, aliases, curation references and source descriptions, and
uses only canonical top-level `relations`. Node-local duplicate edges are omitted.
The page shows ontology version, source SHA-256 and a pinned GitHub source link
only when the source bytes match a committed revision. It makes no claim that
a deployed MCP is currently using the same snapshot.

Generated data is checked in for static hosting. Local, stage and production
web deployment refresh it automatically; `prepare` also refreshes it. No corpus
catalog, chunks, vectors or entity artifacts are read or rebuilt by this exporter.

```bash
python3 ops/export_mcp_explorer.py          # refresh just the static projection
python3 ops/export_mcp_explorer.py --check  # reject a stale projection
./deploy.sh local                         # refresh and serve the existing web app
```

Open `/mcp-explorer.html` on the local URL printed by the wrapper (normally
`http://127.0.0.1:8890`). This is web deployment, separate from `make up` and
retrieval-service deployment. Nothing changes on the Sanchaya production host.

## Interaction and accessibility

Start with Dhaniṣṭhā's immediate neighbourhood. Search names/aliases with
Latin diacritic folding while preserving Devanagari vowel signs. Select a node
for details; **Explore this entity** recentres the graph; **Expand neighbours**
adds another hop. Filters control entity type, relation and direction. The focus
entity stays visible when filtering types. Full overview groups by type, hides
node labels initially and disables neighbourhood-specific direction filtering.

Arrows and the relationship table read source → relation → destination.
Selected-entity details list all its relationships, independently of graph
filters. Entity source references are curation metadata, not edge-level proof;
paths without an actual URL remain text. No corpus hits are inferred from edges.

Use zoom, pan, fit and reset controls; view links preserve selection, expansions
and filters, and browser history supports Back. Zoom/pan positions and search
text are not persisted. The equivalent table, searchable entity buttons and
node keyboard controls provide alternatives to visual graph exploration.
The layout stacks on narrow screens; wide tables scroll within their panels.

## Acceptance checks

- Projection matches ontology bytes; all canonical edges resolve; aliases and
  attributes retain their display forms. Failure produces an actionable message.
- Dhaniṣṭhā shows Vasu and the Makara/Kumbha/Jāradgavīvīthī connections.
  Āryabhaṭa → Āryabhaṭīya traversal preserves incoming authorship direction;
  composition location belongs to the work.
- Filters, expansion, overview, search, shared views and Back agree with the
  graph/table; empty results remain understandable.
- Desktop/mobile layout, keyboard operation and copying prompts work without
  frontend framework/CDN graph dependencies or credential storage.
- Page/source navigation works in the existing local static-server flow.

Ontology v0.4 curation and live MCP integration remain separate future work.
