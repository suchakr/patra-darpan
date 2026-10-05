/* Static MCP information and curated ontology browsing; no tokens or live retrieval calls. */
(function () {
  "use strict";
  const core = window.McpExplorerCore;
  const $ = id => document.getElementById(id);
  const sections = ["overview", "ontology", "connect", "coverage"];
  const defaultEntity = "jyotisha:nakshatra_dhanishtha";
  const palette = ["#307961", "#647ab8", "#bd8443", "#9377ad", "#bd6860", "#548d9c", "#809850", "#958374", "#937449"];
  let model, state, viewBox, positions, noticeTimer, drag;
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function button(text, action) {
    const node = element("button", text); node.type = "button"; node.addEventListener("click", action); return node;
  }
  function notify(message) {
    $("notification").textContent = message; $("notification").classList.add("visible");
    clearTimeout(noticeTimer); noticeTimer = setTimeout(() => $("notification").classList.remove("visible"), 3200);
  }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); notify("Copied to clipboard"); }
    catch {
      notify("Clipboard unavailable. Select the source text and copy it manually.");
    }
  }
  function setSection(section) {
    sections.forEach(name => $(name).hidden = name !== section);
    document.querySelectorAll("[data-section]").forEach(link => {
      if (link.dataset.section === section) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }
  function readState() {
    const params = new URLSearchParams(location.hash.slice(1));
    const section = sections.includes(params.get("section")) ? params.get("section") : "overview";
    const focus = model && model.entities.has(params.get("entity")) ? params.get("entity") : defaultEntity;
    const selected = model && model.entities.has(params.get("selected")) ? params.get("selected") : focus;
    const roots = (params.get("expanded") || "").split(",").filter(id => model && model.entities.has(id));
    return { section, focus, selected, roots: [...new Set([focus, ...roots])],
      view: params.get("view") === "overview" ? "overview" : "neighbourhood",
      type: model && model.typeLabels.has(params.get("type")) ? params.get("type") : "",
      relation: model && model.relationLabels.has(params.get("relation")) ? params.get("relation") : "",
      direction: ["incoming", "outgoing"].includes(params.get("direction")) ? params.get("direction") : "both",
      labels: params.get("labels") !== "off" };
  }
  function saveState(replace = false) {
    const params = new URLSearchParams({ section: state.section });
    if (state.section === "ontology") {
      params.set("entity", state.focus);
      if (state.selected !== state.focus) params.set("selected", state.selected);
      if (state.roots.length > 1) params.set("expanded", state.roots.filter(id => id !== state.focus).join(","));
      if (state.view === "overview") params.set("view", "overview");
      if (state.type) params.set("type", state.type);
      if (state.relation) params.set("relation", state.relation);
      if (state.direction !== "both") params.set("direction", state.direction);
      if (!state.labels) params.set("labels", "off");
    }
    const url = `#${params}`;
    if (location.hash !== url) history[replace ? "replaceState" : "pushState"](null, "", url);
    setSection(state.section);
  }
  function focusEntity(id, clearFilters = false) {
    state.focus = id; state.selected = id; state.roots = [id]; state.section = "ontology";
    state.view = "neighbourhood"; state.labels = true;
    if (clearFilters) { state.type = ""; state.relation = ""; state.direction = "both"; $("entity-search").value = ""; }
    saveState(); render();
  }
  function color(type) { return palette[[...model.typeLabels.keys()].indexOf(type) % palette.length] || palette[0]; }
  function renderSearch() {
    const results = core.search(model, $("entity-search").value, state.type);
    $("search-count").textContent = `${results.length} matching ${results.length === 1 ? "entity" : "entities"}`;
    const list = $("entity-results"); list.replaceChildren();
    for (const { entity } of results) {
      const row = element("li");
      const choose = button(entity.preferred_label, () => focusEntity(entity.id));
      choose.setAttribute("aria-pressed", String(entity.id === state.selected));
      choose.append(element("small", model.typeLabels.get(entity.type) || entity.type));
      row.append(choose); list.append(row);
    }
    if (!results.length) list.append(element("li", "No matching name or alias. Try another form.", "small-meta"));
  }
  function renderDetails() {
    const entity = model.entities.get(state.selected);
    const panel = $("entity-details"); panel.replaceChildren();
    panel.append(element("span", model.typeLabels.get(entity.type) || entity.type, "entity-type"), element("h3", entity.preferred_label), element("p", entity.id, "canonical-id"));
    const actions = element("div", undefined, "details-actions");
    actions.append(button("Explore this entity", () => focusEntity(entity.id)), button("Expand neighbours", () => {
      state.view = "neighbourhood"; state.roots = [...new Set([...state.roots, entity.id])]; saveState(); render();
    }));
    panel.append(actions);
    panel.append(element("h4", "Names and aliases"));
    const aliases = element("div", undefined, "aliases");
    (entity.aliases || []).forEach(alias => aliases.append(element("span", alias)));
    if (!aliases.childElementCount) aliases.append(element("span", "No additional aliases"));
    panel.append(aliases, element("h4", "Attributes"));
    const attrs = Object.entries(entity.attributes || {});
    const attrList = element("dl", undefined, "attributes");
    attrs.forEach(([key, value]) => {
      const pair = element("div"); pair.append(element("dt", core.humanize(key)), element("dd", typeof value === "object" ? JSON.stringify(value) : String(value))); attrList.append(pair);
    });
    panel.append(attrs.length ? attrList : element("p", "No attributes recorded in this snapshot.", "small-meta"));
    const relations = core.relationships(model, entity.id);
    panel.append(element("h4", `All relationships (${relations.length})`));
    const list = element("ul", undefined, "detail-relations");
    relations.forEach(edge => {
      const row = element("li");
      row.append(element("span", `${edge.direction === "incoming" ? "← Incoming" : "→ Outgoing"} · ${model.relationLabels.get(edge.type)} · `), button(edge.target.preferred_label, () => focusEntity(edge.target.id)));
      if (edge.comment) row.title = edge.comment;
      list.append(row);
    });
    panel.append(relations.length ? list : element("p", "No relationships recorded.", "small-meta"));
    panel.append(element("h4", "Curation and provenance"));
    const provenance = element("div", undefined, "provenance");
    provenance.append(element("p", `Status: ${core.humanize(entity.curation_status || "not specified")}`));
    if (entity.source_ref) {
      provenance.append(element("code", entity.source_ref));
      const source = model.data.sources.find(row => row.id === entity.source_ref.split("#")[0]);
      if (source) provenance.append(element("p", source.description), element("code", source.path));
    } else provenance.append(element("p", "No entity source reference supplied."));
    if (entity.comment) { const note = element("details"); note.append(element("summary", "Curation note"), element("p", entity.comment)); provenance.append(note); }
    provenance.append(element("p", "Curated assertions, not passage evidence. Entity provenance is not an individual citation for each relationship."));
    panel.append(provenance);
  }
  function layout(nodes) {
    const result = new Map();
    if (state.view === "overview") {
      const types = [...new Set(nodes.map(entity => entity.type))];
      types.forEach((type, i) => {
        const group = nodes.filter(entity => entity.type === type);
        group.forEach((entity, j) => result.set(entity.id, { x: 100 + (i % 3) * 500 + (j % 5) * 82, y: 120 + Math.floor(i / 3) * 560 + Math.floor(j / 5) * 74 }));
      });
    } else {
      const sorted = [...nodes].sort((a, b) => a.preferred_label.localeCompare(b.preferred_label));
      const neighbours = new Set(core.graph(model, { ...state, roots: [state.focus] }).nodes.map(entity => entity.id));
      result.set(state.focus, { x: 600, y: 425 });
      for (const ring of [1, 2]) {
        const group = sorted.filter(entity => entity.id !== state.focus && (neighbours.has(entity.id) ? 1 : 2) === ring);
        group.forEach((entity, i) => {
          const angle = -Math.PI / 2 + i * Math.PI * 2 / group.length;
          const radius = ring === 1 ? Math.max(240, group.length * 22) : Math.max(500, group.length * 25);
          result.set(entity.id, { x: 600 + Math.cos(angle) * radius, y: 425 + Math.sin(angle) * radius });
        });
      }
    }
    return result;
  }
  function svgNode(tag, attributes = {}, text) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function setViewBox(box) { viewBox = box; $("ontology-graph").setAttribute("viewBox", `${box.x} ${box.y} ${box.w} ${box.h}`); }
  function fit() {
    const values = [...positions.values()];
    if (!values.length) { setViewBox({ x: 0, y: 0, w: 1200, h: 850 }); return; }
    const minX = Math.min(...values.map(p => p.x)), maxX = Math.max(...values.map(p => p.x));
    const minY = Math.min(...values.map(p => p.y)), maxY = Math.max(...values.map(p => p.y));
    const rect = $("ontology-graph").getBoundingClientRect();
    const padding = rect.width && rect.width < 500 ? 60 : 140;
    let w = Math.max(480, maxX - minX + padding * 2);
    let h = Math.max(440, maxY - minY + 160);
    const ratio = rect.width && rect.height ? rect.width / rect.height : 1.4;
    if (w / h < ratio) w = h * ratio; else h = w / ratio;
    setViewBox({ x: (minX + maxX - w) / 2, y: (minY + maxY - h) / 2, w, h });
  }
  function zoom(factor) {
    if (!viewBox) return;
    const w = Math.max(140, Math.min(6000, viewBox.w * factor));
    const h = viewBox.h * w / viewBox.w;
    setViewBox({ x: viewBox.x + (viewBox.w - w) / 2, y: viewBox.y + (viewBox.h - h) / 2, w, h });
  }
  function renderGraph() {
    const graph = core.graph(model, state);
    positions = layout(graph.nodes);
    const svg = $("ontology-graph"); svg.replaceChildren();
    const defs = svgNode("defs"); const marker = svgNode("marker", { id: "edge-arrow", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" });
    marker.append(svgNode("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#83988d" })); defs.append(marker); svg.append(defs);
    for (const edge of graph.edges) {
      const from = positions.get(edge.from), to = positions.get(edge.to);
      const dx = to.x - from.x, dy = to.y - from.y, length = Math.hypot(dx, dy) || 1;
      const radius = state.view === "overview" ? 20 : 28;
      const line = svgNode("line", { x1: from.x + dx / length * radius, y1: from.y + dy / length * radius, x2: to.x - dx / length * (radius + 5), y2: to.y - dy / length * (radius + 5), "marker-end": "url(#edge-arrow)", class: `graph-edge${edge.from === state.selected || edge.to === state.selected ? " highlight" : ""}` });
      line.append(svgNode("title", {}, `${model.entities.get(edge.from).preferred_label} → ${model.relationLabels.get(edge.type)} → ${model.entities.get(edge.to).preferred_label}`)); svg.append(line);
      if (state.view !== "overview") svg.append(svgNode("text", { x: from.x + dx * .65, y: from.y + dy * .65 + (Math.abs(dx) > 30 ? 12 : -8), "text-anchor": "middle", class: "edge-label" }, model.relationLabels.get(edge.type)));
    }
    if (state.view === "overview") {
      const types = [...new Set(graph.nodes.map(entity => entity.type))];
      types.forEach((type, i) => svg.append(svgNode("text", { x: 100 + (i % 3) * 500, y: 65 + Math.floor(i / 3) * 560, class: "cluster-label" }, model.typeLabels.get(type) || type)));
    }
    for (const entity of graph.nodes) {
      const point = positions.get(entity.id);
      const group = svgNode("g", { transform: `translate(${point.x},${point.y})`, class: `graph-node${entity.id === state.selected ? " selected" : ""}`, role: "button", tabindex: 0, "aria-label": `Inspect ${entity.preferred_label}`, "aria-pressed": String(entity.id === state.selected) });
      group.append(svgNode("circle", { r: state.view === "overview" ? 17 : entity.id === state.focus ? 28 : 22, fill: color(entity.type) }), svgNode("title", {}, `${entity.preferred_label} · ${model.typeLabels.get(entity.type) || entity.type}`));
      if (state.labels || entity.id === state.selected) {
        const label = svgNode("text", { y: state.view === "overview" ? 34 : 48, "text-anchor": "middle" });
        const words = entity.preferred_label.split(" ");
        if (entity.preferred_label.length > 24 && words.length > 1) {
          const mid = Math.ceil(words.length / 2);
          label.append(svgNode("tspan", { x: 0 }, words.slice(0, mid).join(" ")), svgNode("tspan", { x: 0, dy: "1.1em" }, words.slice(mid).join(" ")));
        } else label.textContent = entity.preferred_label;
        group.append(label);
      }
      const select = () => { state.selected = entity.id; saveState(); render(false); };
      group.addEventListener("click", select);
      group.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); $("ontology-graph").querySelector(".graph-node.selected")?.focus({ preventScroll: true }); } });
      svg.append(group);
    }
    $("graph-summary").textContent = `${graph.nodes.length} visible entities · ${graph.edges.length} relationships${state.view === "overview" ? " · Direction filter applies to neighbourhoods only" : " · Focus entity stays visible when filtering types"}`;
    $("graph-title").textContent = state.view === "overview" ? "Ontology overview" : model.entities.get(state.focus).preferred_label;
    const rows = $("relationship-rows"); rows.replaceChildren();
    graph.edges.forEach(edge => {
      const row = element("tr"), from = element("td"), relation = element("td", model.relationLabels.get(edge.type)), to = element("td");
      from.append(button(model.entities.get(edge.from).preferred_label, () => focusEntity(edge.from)));
      to.append(button(model.entities.get(edge.to).preferred_label, () => focusEntity(edge.to)));
      row.append(from, relation, to); rows.append(row);
    });
    if (!graph.edges.length) { const row = element("tr"), cell = element("td", "No relationships in this view. Try clearing filters or exploring another entity."); cell.colSpan = 3; row.append(cell); rows.append(row); }
    const legend = $("graph-legend"); legend.replaceChildren();
    [...new Set(graph.nodes.map(entity => entity.type))].forEach(type => { const item = element("span"); const dot = element("i"); dot.style.background = color(type); item.append(dot, document.createTextNode(model.typeLabels.get(type) || type)); legend.append(item); });
  }
  function render(resetViewport = true) {
    $("type-filter").value = state.type; $("relation-filter").value = state.relation;
    $("direction-filter").value = state.direction; $("direction-filter").disabled = state.view === "overview";
    $("show-labels").checked = state.labels;
    $("neighbourhood-button").setAttribute("aria-pressed", String(state.view !== "overview"));
    $("overview-button").setAttribute("aria-pressed", String(state.view === "overview"));
    renderSearch(); renderDetails(); renderGraph(); if (resetViewport) fit();
  }
  document.querySelector(".skip-link").addEventListener("click", event => {
    event.preventDefault(); $("main").setAttribute("tabindex", "-1"); $("main").focus();
  });
  document.querySelectorAll("[data-section]").forEach(link => link.addEventListener("click", event => {
    event.preventDefault(); if (!model) { location.hash = `section=${link.dataset.section}`; return; }
    state.section = link.dataset.section; saveState(); if (state.section === "ontology") render();
  }));
  document.querySelectorAll("[data-copy-target]").forEach(node => node.addEventListener("click", () => copy($(node.dataset.copyTarget).textContent)));
  window.addEventListener("hashchange", () => { if (!model) { setSection(readState().section); return; } state = readState(); setSection(state.section); if (state.section === "ontology") render(); });
  window.addEventListener("popstate", () => { if (model) { state = readState(); setSection(state.section); if (state.section === "ontology") render(); } });
  setSection(readState().section);
  fetch("assets/data/mcp-ontology.json").then(response => {
    if (!response.ok) throw new Error(`Ontology snapshot could not be loaded (HTTP ${response.status})`);
    return response.json();
  }).then(data => {
    model = core.index(data); state = readState();
    if (!model.entities.has(state.focus)) { state.focus = data.entities[0].id; state.selected = state.focus; state.roots = [state.focus]; }
    $("version-badge").textContent = `Ontology v${data.version} · static snapshot`;
    $("ontology-counts").textContent = `${data.entities.length} entities · ${data.relations.length} relationships`;
    const source = element("a", `Ontology v${data.version} · source ${data.source_sha256.slice(0, 8)} ↗`);
    if (data.source_commit) {
      source.href = `https://github.com/suchakr/patra-darpan/blob/${data.source_commit}/${data.source_file}`;
      source.target = "_blank"; source.rel = "noopener noreferrer"; $("snapshot-source").replaceChildren(source);
    } else $("snapshot-source").textContent = `Local ontology snapshot · ${data.source_sha256.slice(0, 8)} · no committed source link`;
    for (const [id, label] of model.typeLabels) $("type-filter").append(new Option(label, id));
    const usedRelations = new Set(data.relations.map(edge => edge.type));
    for (const [id, label] of model.relationLabels) if (usedRelations.has(id)) $("relation-filter").append(new Option(label, id));
    $("entity-search").addEventListener("input", renderSearch);
    document.querySelectorAll("[data-example]").forEach(node => node.addEventListener("click", () => focusEntity(node.dataset.example, true)));
    for (const [control, key] of [["type-filter", "type"], ["relation-filter", "relation"], ["direction-filter", "direction"]]) $(control).addEventListener("change", event => { state[key] = event.target.value; saveState(); render(); });
    $("overview-button").addEventListener("click", () => { state.view = "overview"; state.labels = false; saveState(); render(); });
    $("neighbourhood-button").addEventListener("click", () => { state.view = "neighbourhood"; state.labels = true; saveState(); render(); });
    $("show-labels").addEventListener("change", event => { state.labels = event.target.checked; saveState(); render(false); });
    $("zoom-in").addEventListener("click", () => zoom(.8)); $("zoom-out").addEventListener("click", () => zoom(1.25));
    $("fit-graph").addEventListener("click", fit); $("reset-graph").addEventListener("click", () => focusEntity(state.focus, true));
    $("share-view").addEventListener("click", () => copy(location.href));
    const svg = $("ontology-graph");
    svg.addEventListener("wheel", event => { if (event.ctrlKey) { event.preventDefault(); zoom(event.deltaY > 0 ? 1.1 : .9); } }, { passive: false });
    svg.addEventListener("pointerdown", event => {
      if (event.button !== 0 || event.target.closest(".graph-node") || !viewBox) return;
      drag = { x: event.clientX, y: event.clientY, box: { ...viewBox }, pointer: event.pointerId };
      svg.setPointerCapture(event.pointerId);
    });
    svg.addEventListener("pointermove", event => {
      if (!drag) return; const rect = svg.getBoundingClientRect();
      setViewBox({ ...drag.box, x: drag.box.x - (event.clientX - drag.x) * drag.box.w / rect.width, y: drag.box.y - (event.clientY - drag.y) * drag.box.h / rect.height });
    });
    svg.addEventListener("pointerup", () => { drag = null; }); svg.addEventListener("pointercancel", () => { drag = null; });
    setSection(state.section); render();
  }).catch(error => { $("data-error").hidden = false; $("data-error").textContent = `${error.message}. Try reloading this page or contact the service operator.`; $("ontology-counts").textContent = "Ontology unavailable"; });
})();
