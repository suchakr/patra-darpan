/* Pure graph/search functions shared by the browser and small data-contract checks. */
(function (root) {
  "use strict";
  const relationLabels = {
    associated_with_rasi: "Associated with rāśi", associated_with_place: "Associated with place",
    located_in_veethi: "Located in vīthī", subdivision_of_marga: "Subdivision of mārga",
    authored_by: "Authored by", composed_at: "Composed at", described_in: "Described in",
    associated_season: "Associated season", ruled_by: "Ruled by", instrument_used_for: "Instrument used for",
    relates_to_event: "Relates to event"
  };
  const normalize = value => String(value).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  const humanize = value => String(value).replaceAll("_", " ");
  function index(data) {
    const entities = new Map(data.entities.map(entity => [entity.id, entity]));
    if (entities.size !== data.entities.length) throw new Error("Duplicate entity identifiers");
    for (const edge of data.relations) {
      if (!entities.has(edge.from) || !entities.has(edge.to)) throw new Error("Unknown relationship endpoint");
    }
    return {
      data, entities,
      typeLabels: new Map(data.entity_types.map(type => [type.id, type.id === "lunar_mansion" ? "Nakṣatra" : type.label])),
      relationLabels: new Map(data.relation_types.map(type => [type.id, relationLabels[type.id] || type.label || humanize(type.id)]))
    };
  }
  function search(model, query, type = "") {
    const term = normalize(query);
    return model.data.entities.filter(entity => !type || entity.type === type).map(entity => {
      const forms = [entity.preferred_label, ...(entity.aliases || [])].map(normalize);
      const score = !term ? 3 : forms[0] === term ? 0 : forms.includes(term) ? 1 : forms.some(form => form.includes(term)) || normalize(entity.id).includes(term) ? 2 : 9;
      return { entity, score };
    }).filter(row => row.score < 9).sort((a, b) => a.score - b.score || a.entity.preferred_label.localeCompare(b.entity.preferred_label));
  }
  function graph(model, state) {
    const roots = new Set((state.roots || [state.focus]).filter(id => model.entities.has(id)));
    const allowed = entity => !state.type || entity.type === state.type || (state.view !== "overview" && entity.id === state.focus);
    let edges = model.data.relations.filter(edge => !state.relation || edge.type === state.relation);
    let nodes;
    if (state.view === "overview") {
      nodes = model.data.entities.filter(allowed);
    } else {
      const visible = new Set([...roots].filter(id => allowed(model.entities.get(id))));
      edges = edges.filter(edge => state.direction === "incoming" ? roots.has(edge.to) : state.direction === "outgoing" ? roots.has(edge.from) : roots.has(edge.from) || roots.has(edge.to));
      for (const edge of edges) {
        if (allowed(model.entities.get(edge.from)) && allowed(model.entities.get(edge.to))) {
          visible.add(edge.from); visible.add(edge.to);
        }
      }
      nodes = [...visible].map(id => model.entities.get(id));
    }
    const ids = new Set(nodes.map(entity => entity.id));
    return { nodes, edges: edges.filter(edge => ids.has(edge.from) && ids.has(edge.to)) };
  }
  function relationships(model, id) {
    return model.data.relations.filter(edge => edge.from === id || edge.to === id).map(edge => ({
      ...edge, direction: edge.from === id ? "outgoing" : "incoming",
      target: model.entities.get(edge.from === id ? edge.to : edge.from)
    }));
  }
  const api = { index, search, graph, relationships, normalize, humanize };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.McpExplorerCore = api;
})(typeof globalThis === "undefined" ? this : globalThis);
