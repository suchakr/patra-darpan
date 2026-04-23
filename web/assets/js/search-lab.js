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
    "trigonometric tables",
    "Yuktibhasa Jyesthadeva",
    "Vrddha Gargiya Jyotisa",
    "Brahmanda Purana",
    "Dhruva pole star",
    "Parashara comets",
    "Eclipse period 3339",
    "Krishna lore",
    "Agastya heliacal visibility",
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

  function getRemoteUrl(chunk) {
    return chunk.remote_url || chunk.source_url || "";
  }

  function getJuUrl(chunk) {
    return chunk.ju_url || "";
  }

  function getGcsArchiveLink(chunk) {
    if (!chunk.gcs_key) return "";
    return `/.netlify/functions/authorize-pdf?file=${encodeURIComponent(`assets/${chunk.gcs_key}`)}`;
  }

  function sameLink(left, right) {
    return Boolean(left && right && left === right);
  }

  function getAccessIcon(kind) {
    const icons = {
      source:
        '<svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>',
      mirror:
        '<svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="5" width="7" height="14" rx="1.5"></rect><rect x="13" y="5" width="7" height="14" rx="1.5"></rect><path d="M11 12h2"></path></svg>',
      archive:
        '<svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2"></rect><path d="M4 16V6a2 2 0 0 1 2-2h10"></path></svg>',
    };
    return icons[kind] || icons.archive;
  }

  function accessTargets(chunk) {
    const remoteUrl = getRemoteUrl(chunk);
    const juUrl = getJuUrl(chunk);
    const archiveUrl = getGcsArchiveLink(chunk);
    const primary = juUrl || archiveUrl || remoteUrl || "";
    const targets = [];

    function addTarget(id, kind, label, href, active) {
      if (!href) return;
      if (targets.some((target) => sameLink(target.href, href))) return;
      targets.push({ id, kind, label, href, active: Boolean(active) });
    }

    addTarget("mirror", "mirror", "CAHC mirror", juUrl, sameLink(primary, juUrl));
    addTarget("archive", "archive", "Archive copy", archiveUrl, sameLink(primary, archiveUrl));
    addTarget("source", "source", "Original source", remoteUrl, sameLink(primary, remoteUrl));
    return targets;
  }

  function renderAccessChips(container, chunk, prefix) {
    const targets = accessTargets(chunk);
    if (!targets.length) return false;

    const group = document.createElement("div");
    group.className = "link-source-chips";
    group.setAttribute("aria-label", prefix ? `${prefix} access options` : "Access options");

    targets.forEach((target) => {
      const link = document.createElement("a");
      link.href = target.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.className = `link-source-chip chip-${target.id}${target.active ? " active" : ""}`;
      link.title = target.label + (target.active ? " default" : "");
      link.setAttribute("aria-label", link.title);
      link.innerHTML = getAccessIcon(target.kind);
      group.appendChild(link);
    });

    container.appendChild(group);
    return true;
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

  function makeQualityNotesChip(warnings) {
    const chip = makeChip(`Quality notes: ${warnings.length}`, "chip quality-note");
    const detail = `Extraction quality notes: ${warnings.join(", ")}. Search hit may still be valid; inspect the source PDF for evidence use.`;
    chip.title = detail;
    chip.tabIndex = 0;
    chip.setAttribute("data-tooltip", detail);
    return chip;
  }

  function summarizeText(text) {
    const clean = String(text || "").replace(/\s+/g, " ").trim();
    if (clean.length <= 360) return clean;
    return `${clean.slice(0, 360).trim()}...`;
  }

  function stripMarkdown(text) {
    return String(text || "")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1")
      .replace(/__([^_]+)__/g, "$1")
      .replace(/_([^_]+)_/g, "$1")
      .trim();
  }

  function tableRows(markdown) {
    return String(markdown || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .filter((line, index) => index !== 1)
      .map((line) => line.replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => stripMarkdown(cell)));
  }

  function renderTable(markdown) {
    const rows = tableRows(markdown);
    if (!rows.length) return document.createTextNode("");
    const tableWrap = document.createElement("div");
    tableWrap.className = "table-preview";
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    rows[0].forEach((cell) => {
      const th = document.createElement("th");
      th.textContent = cell;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    rows.slice(1).forEach((row) => {
      const tr = document.createElement("tr");
      row.forEach((cell) => {
        const td = document.createElement("td");
        td.textContent = cell;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    return tableWrap;
  }

  function typesetMath(node) {
    if (window.MathJax && typeof window.MathJax.typesetPromise === "function") {
      window.MathJax.typesetPromise([node]).catch(() => {});
    } else {
      window.setTimeout(() => {
        if (window.MathJax && typeof window.MathJax.typesetPromise === "function") {
          window.MathJax.typesetPromise([node]).catch(() => {});
        }
      }, 500);
    }
  }

  function togglePanel(button, panel, renderContent) {
    const expanded = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", expanded ? "false" : "true");
    panel.hidden = expanded;
    if (!expanded && !panel.hasChildNodes()) {
      renderContent(panel);
      typesetMath(panel);
    }
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

  function renderContext(container, result, direction) {
    container.textContent = "";
    const config =
      direction === "prev"
        ? ["Previous context", result.chunk.prev_chunk_id]
        : ["Next context", result.chunk.next_chunk_id];
    const [label, chunkId] = config;
    const chunk = chunkId ? state.chunkMap.get(chunkId) : null;
    if (!chunk) return;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "context-chip";
    button.setAttribute("aria-expanded", "false");
    button.textContent = `${label}: ${SearchCore.headingText(chunk) || chunk.chunk_id}`;
    const panel = document.createElement("div");
    panel.className = "context-preview";
    panel.hidden = true;
    button.addEventListener("click", () => {
      togglePanel(button, panel, (target) => {
        const heading = document.createElement("strong");
        heading.textContent = chunk.chunk_id;
        const excerpt = document.createElement("p");
        excerpt.textContent = summarizeText(chunk.text);
        target.appendChild(heading);
        target.appendChild(excerpt);
      });
    });
    container.appendChild(button);
    container.appendChild(panel);
  }

  function highlightForQuery(text) {
    return SearchCore.highlightText(text || "", SearchCore.tokenize(state.lastQuery));
  }

  function renderActions(container, chunk) {
    container.textContent = "";
    renderAccessChips(container, chunk, "PDF");

    const cite = document.createElement("button");
    cite.type = "button";
    cite.className = "copy-cite-button";
    cite.textContent = `Copy citation key ${chunk.chunk_id}`;
    cite.title = "Copy this stable citation key";
    cite.setAttribute("aria-label", `Copy citation key ${chunk.chunk_id}`);
    cite.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(chunk.chunk_id);
        cite.textContent = "Copied citation key";
        window.setTimeout(() => {
          cite.textContent = `Copy citation key ${chunk.chunk_id}`;
        }, 900);
      } catch {
        cite.textContent = `Copy citation key ${chunk.chunk_id}`;
      }
    });
    container.appendChild(cite);
  }

  function renderAttachmentPanel(panel, attachment, chunk) {
    if (attachment.type === "table") {
      panel.appendChild(renderTable(attachment.markdown));
      return;
    }

    const caption = document.createElement("p");
    caption.textContent = attachment.caption || "No caption available.";

    if (attachment.type === "figure" && attachment.web_path) {
      const figure = document.createElement("figure");
      const img = document.createElement("img");
      img.src = attachment.web_path;
      img.alt = attachment.caption || "Decoded figure";
      img.loading = "lazy";
      const figcaption = document.createElement("figcaption");
      figcaption.textContent = attachment.caption || attachment.source_path || "";
      figure.appendChild(img);
      figure.appendChild(figcaption);
      panel.appendChild(figure);
      return;
    }

    panel.appendChild(caption);
    renderAccessChips(panel, chunk, "PDF");
  }

  function renderAttachments(container, chunk) {
    const attachments = Array.isArray(chunk.attachments) ? chunk.attachments : [];
    container.textContent = "";
    if (!attachments.length) return;

    function attachmentIcon(type) {
      if (type === "table") return "▦";
      if (type === "figure") return "◧";
      if (type === "page_image") return "◫";
      return "•";
    }

    attachments.forEach((attachment, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "attachment-chip";
      button.setAttribute("aria-expanded", "false");
      const label = attachment.label || attachment.type || "Attachment";
      const icon = document.createElement("span");
      icon.className = "attachment-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = attachmentIcon(attachment.type);
      const text = document.createElement("span");
      if (attachment.type === "table" && attachment.row_count && attachment.column_count) {
        text.textContent = `${label} ${attachment.row_count}x${attachment.column_count}`;
      } else {
        text.textContent = label;
      }
      button.appendChild(icon);
      button.appendChild(text);
      const panel = document.createElement("div");
      panel.className = "attachment-panel";
      panel.hidden = true;
      panel.id = `${chunk.chunk_id.replace(/[^a-z0-9_-]/gi, "-")}-attachment-${index}`;
      button.setAttribute("aria-controls", panel.id);
      button.addEventListener("click", () => {
        togglePanel(button, panel, (target) => renderAttachmentPanel(target, attachment, chunk));
      });
      container.appendChild(button);
      container.appendChild(panel);
    });
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
    if (Array.isArray(chunk.attachments) && chunk.attachments.length) {
      node.classList.add("has-attachments");
    }
    node.querySelector(".result-rank").textContent = rank;
    node.querySelector("h2").innerHTML = highlightForQuery(SearchCore.headingText(chunk) || chunk.title || chunk.doc_id);
    node.querySelector(".heading-path").textContent = chunk.chunk_id;
    node.querySelector(".snippet").innerHTML = result.snippet_html;

    const meta = node.querySelector(".result-meta");
    meta.appendChild(makeChip(`score ${result.score.toFixed(1)}`));
    meta.appendChild(makeChip(`chunk ${chunk.chunk_ordinal}`));
    if (chunk.quality_warnings && chunk.quality_warnings.length) {
      meta.appendChild(makeQualityNotesChip(chunk.quality_warnings));
    }

    renderContext(node.querySelector(".prev-context-row"), result, "prev");
    renderContext(node.querySelector(".next-context-row"), result, "next");
    renderAttachments(node.querySelector(".attachment-row"), chunk);
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
