# Jyotisha ontology snapshots

These are repository-owned, versioned ontology artifacts for the retrieval
pilot (originally developed under the ISCLS event name).
The build and MCP use an explicit versioned file; scratch directories are not
runtime or build dependencies.

| File | Role |
| --- | --- |
| `jyotisha-starter.json` | Historical 16-entity reference copied from the original v0 example. |
| `jyotisha-v0.1.json` | Normalized 16-entity seed snapshot with provenance and curation fields. |
| `jyotisha-v0.2.json` | 143 entities and 632 normalized aliases; no graph edges. |
| `jyotisha-v0.3.json` | v0.2 plus 147 typed graph edges and local relation projections. |
| `jyotisha-v0.3.1.json` | v0.3 with 18 alias-level ambiguity markers and three approved data edits; v0.3 remains the active pilot input pending a separate release decision. |

The active pilot input is `jyotisha-v0.3.json`. Versioned files are immutable
snapshots; create a new version when the contract or vocabulary changes.

The v0.3 graph currently contains 11 populated relationship types. Top-level
`relations` is canonical; `entity.relations` is a rebuildable read projection.
Some historical and corpus-derived edges remain pilot assertions and require
edge-level provenance before they are treated as authoritative.

The v0.3.1 snapshot removes the alias `क्रित्तिका` from Kṛttikā, normalizes
Abhijit's daivata to `Brahmā`, and changes Aśvinī's daivata to `Aśvinau`. That
last correction intentionally departs from the source CSV value `Aśvini`: the
approved value reflects the dual Aśvins, and the deviation is recorded in the
entity's `v031_changes` field. Ambiguity markers identify forms for disclosure;
they do not establish that an occurrence is a false positive or resolve its
contextual sense.
