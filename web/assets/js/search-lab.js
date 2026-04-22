(function () {
  "use strict";

  const state = {
    corpus: null,
    chunkMap: null,
    lastQuery: "",
    recentSearches: [],
  };

  const RECENT_KEY = "patra-darpan-search-lab-recent";
  const RECENT_LIMIT = 8;
  const SEEDED_QUERIES = [
    "Yajnavalkya cycle",
    "Saptarsi era",
    "pandiagonal magic square",
    "Narayana Pandita",
    "Vedanga Jyotisa solstice",
    "Surya Siddhanta planetary nodes",
    "Jnanaraja sine table",
    "Yuktibhasa Jyesthadeva",
  ];

  const elements = {
    stats: document.getElementById("corpus-stats"),
    form: document.getElementById("search-form"),
    query: document.getElementById("search-query"),
    count: document.getElementById("result-count"),
    results: document.getElementById("results"),
    template: document.getElementById("result-template"),
    suggestions: document.getElementById("query-suggestions"),
  };

  function sourceHref(chunk) {
    if (chunk.source_url) return chunk.source_url;
    if (chunk.gcs_key) {
      return `/.netlify/functions/authorize-pdf?file=${encodeURIComponent(`assets/${chunk.gcs_key}`)}`;
    }
    return "";
  }

  function archiveHref(chunk) {
    if (!chunk.gcs_key) return "";
    return `/.netlify/functions/authorize-pdf?file=${encodeURIComponent(`assets/${chunk.gcs_key}`)}`;
  }

  function setStatus(message) {
    elements.count.textContent = message;
  }

  function renderStats() {
    const metadata = state.corpus.metadata || {};
    const sets = metadata.selected_sets && metadata.selected_sets.length ? metadata.selected_sets.join(", ") : "custom";
    elements.stats.textContent = `${metadata.doc_count || 0} docs · ${metadata.chunk_count || 0} chunks · ${sets}`;
  }

  function makeChip(text, className) {
    const chip = document.createElement("span");
    chip.className = className || "chip";
    chip.textContent = text;
    return chip;
  }

  function loadRecentSearches() {
    try {
      const parsed = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
      if (!Array.isArray(parsed) || !parsed.length) return SEEDED_QUERIES.slice();
      const cleaned = parsed.filter((item) => typeof item === "string" && item.trim()).slice(0, RECENT_LIMIT);
      return cleaned.length ? cleaned : SEEDED_QUERIES.slice();
    } catch {
      return SEEDED_QUERIES.slice();
    }
  }

  function saveRecentSearches() {
    localStorage.setItem(RECENT_KEY, JSON.stringify(state.recentSearches.slice(0, RECENT_LIMIT)));
  }

  function rememberSearch(query) {
    const clean = String(query || "").trim();
    if (clean.length < 2) return;
    state.recentSearches = state.recentSearches.filter((item) => item.toLowerCase() !== clean.toLowerCase());
    state.recentSearches.unshift(clean);
    state.recentSearches = state.recentSearches.slice(0, RECENT_LIMIT);
    saveRecentSearches();
    renderSuggestions();
  }

  function renderSuggestions() {
    elements.suggestions.textContent = "";
    const label = document.createElement("span");
    label.className = "suggestion-label";
    label.textContent = "Try";
    elements.suggestions.appendChild(label);

    state.recentSearches.slice(0, RECENT_LIMIT).forEach((query) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "suggestion-chip";
      button.textContent = query;
      button.addEventListener("click", () => {
        elements.query.value = query;
        rememberSearch(query);
        renderResults(query);
      });
      elements.suggestions.appendChild(button);
    });
  }

  function renderContext(container, result) {
    const neighbors = SearchCore.getNeighborHeadings(result.chunk, state.chunkMap);
    container.textContent = "";
    if (!neighbors.prev && !neighbors.next) return;

    if (neighbors.prev) {
      const prev = makeChip(`Prev: ${neighbors.prev.heading || neighbors.prev.chunk_id}`, "context-chip");
      container.appendChild(prev);
    }
    if (neighbors.next) {
      const next = makeChip(`Next: ${neighbors.next.heading || neighbors.next.chunk_id}`, "context-chip");
      container.appendChild(next);
    }
  }

  function highlightForQuery(text) {
    return SearchCore.highlightText(text || "", SearchCore.tokenize(state.lastQuery));
  }

  function renderActions(container, chunk) {
    container.textContent = "";
    const source = sourceHref(chunk);
    if (source) {
      const sourceLink = document.createElement("a");
      sourceLink.href = source;
      sourceLink.target = "_blank";
      sourceLink.rel = "noopener noreferrer";
      sourceLink.textContent = "Source PDF";
      container.appendChild(sourceLink);
    }

    const archive = archiveHref(chunk);
    if (archive && archive !== source) {
      const archiveLink = document.createElement("a");
      archiveLink.href = archive;
      archiveLink.target = "_blank";
      archiveLink.rel = "noopener noreferrer";
      archiveLink.textContent = "Archive";
      container.appendChild(archiveLink);
    }

    const cite = document.createElement("button");
    cite.type = "button";
    cite.className = "copy-cite-button";
    cite.textContent = `Copy chunk ID ${chunk.chunk_id}`;
    cite.title = "Copy this cited chunk ID";
    cite.setAttribute("aria-label", `Copy cited chunk ID ${chunk.chunk_id}`);
    cite.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(chunk.chunk_id);
        cite.textContent = "Copied chunk ID";
        window.setTimeout(() => {
          cite.textContent = `Copy chunk ID ${chunk.chunk_id}`;
        }, 900);
      } catch {
        cite.textContent = `Copy chunk ID ${chunk.chunk_id}`;
      }
    });
    container.appendChild(cite);
  }

  function groupResults(results) {
    const groups = [];
    const byDoc = new Map();
    results.forEach((result) => {
      const docId = result.chunk.doc_id;
      if (!byDoc.has(docId)) {
        const group = {
          doc_id: docId,
          title: result.chunk.title || docId,
          author_display: result.chunk.author_display || "",
          year: result.chunk.year || "",
          topScore: result.score,
          results: [],
        };
        byDoc.set(docId, group);
        groups.push(group);
      }
      byDoc.get(docId).results.push(result);
    });
    return groups;
  }

  function renderResultCard(result, rank) {
    const chunk = result.chunk;
    const node = elements.template.content.firstElementChild.cloneNode(true);
    node.querySelector(".result-rank").textContent = rank;
    node.querySelector("h2").innerHTML = highlightForQuery(SearchCore.headingText(chunk) || chunk.title || chunk.doc_id);
    node.querySelector(".heading-path").textContent = chunk.chunk_id;
    node.querySelector(".snippet").innerHTML = result.snippet_html;

    const meta = node.querySelector(".result-meta");
    meta.appendChild(makeChip(`score ${result.score.toFixed(1)}`));
    meta.appendChild(makeChip(`chunk ${chunk.chunk_ordinal}`));
    if (chunk.quality_warnings && chunk.quality_warnings.length) {
      meta.appendChild(makeChip(`${chunk.quality_warnings.length} warnings`, "chip warning"));
    }

    renderContext(node.querySelector(".context-row"), result);
    renderActions(node.querySelector(".result-actions"), chunk);
    return node;
  }

  function renderGroup(group, startRank) {
    const section = document.createElement("section");
    section.className = "result-group";

    const header = document.createElement("button");
    header.type = "button";
    header.className = "group-header";
    header.setAttribute("aria-expanded", "true");
    const title = document.createElement("div");
    title.className = "group-title";
    title.innerHTML = highlightForQuery(group.title);
    const meta = document.createElement("div");
    meta.className = "group-meta";
    meta.textContent = `${group.author_display || "Unknown author"}${group.year ? ` · ${group.year}` : ""} · ${group.results.length} matching chunk${group.results.length === 1 ? "" : "s"} · top score ${group.topScore.toFixed(1)}`;
    const indicator = document.createElement("span");
    indicator.className = "group-toggle-indicator";
    indicator.setAttribute("aria-hidden", "true");
    indicator.textContent = "▾";
    header.appendChild(title);
    header.appendChild(meta);
    header.appendChild(indicator);
    section.appendChild(header);

    const chunks = document.createElement("div");
    chunks.className = "group-chunks";
    const chunksId = `group-chunks-${group.doc_id.replace(/[^a-z0-9_-]/gi, "-")}`;
    chunks.id = chunksId;
    header.setAttribute("aria-controls", chunksId);
    group.results.forEach((result, index) => {
      chunks.appendChild(renderResultCard(result, startRank + index));
    });
    section.appendChild(chunks);

    header.addEventListener("click", () => {
      const collapsed = section.classList.toggle("collapsed");
      header.setAttribute("aria-expanded", collapsed ? "false" : "true");
    });
    return section;
  }

  function renderResults(query) {
    state.lastQuery = query;
    const results = SearchCore.search(state.corpus, query, { limit: 48 });
    elements.results.textContent = "";

    const params = new URLSearchParams(window.location.search);
    if (query) params.set("q", query);
    else params.delete("q");
    window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? `?${params}` : ""}`);

    if (!query) {
      setStatus("Enter a query to search the decoded pilot.");
      return;
    }

    rememberSearch(query);
    const groups = groupResults(results);
    setStatus(`${results.length} chunk${results.length === 1 ? "" : "s"} across ${groups.length} document${groups.length === 1 ? "" : "s"} for “${query}”`);
    if (!results.length) return;

    let rank = 1;
    groups.forEach((group) => {
      elements.results.appendChild(renderGroup(group, rank));
      rank += group.results.length;
    });
  }

  async function loadCorpus() {
    const response = await fetch("assets/data/search-corpus.json");
    if (!response.ok) {
      throw new Error(`Failed to load search corpus: ${response.status}`);
    }
    state.corpus = await response.json();
    state.chunkMap = SearchCore.buildChunkMap(state.corpus);
    renderStats();
  }

  function setupEvents() {
    elements.form.addEventListener("submit", (event) => {
      event.preventDefault();
      renderResults(elements.query.value.trim());
    });
    elements.query.addEventListener("input", () => {
      const query = elements.query.value.trim();
      if (!query) renderResults("");
    });
  }

  async function init() {
    state.recentSearches = loadRecentSearches();
    renderSuggestions();
    setupEvents();
    try {
      await loadCorpus();
      const params = new URLSearchParams(window.location.search);
      const initialQuery = params.get("q") || "";
      if (initialQuery) {
        elements.query.value = initialQuery;
        renderResults(initialQuery);
      } else {
        setStatus("Enter a query to search the decoded pilot.");
      }
      elements.query.focus();
    } catch (error) {
      elements.stats.textContent = "Corpus failed to load";
      setStatus(error.message || "Failed to load search corpus.");
    }
  }

  init();
})();
