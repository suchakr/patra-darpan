const state = {
  docs: [],
  sets: [],
  setMembership: new Map(),
  annotations: {},
  currentDocId: null,
  currentMarkdown: "",
  mode: "raw",
  docFilter: "all",
  setFilter: "",
  compactList: false,
  layout: {
    listWidth: 280,
    pdfWidth: 620,
    mdWidth: 620,
    listCollapsed: false,
    mdZoom: 1,
  },
};

const el = {
  shell: document.getElementById("shell"),
  docs: document.getElementById("docs"),
  docCount: document.getElementById("doc-count"),
  filter: document.getElementById("filter"),
  statusFilters: document.querySelectorAll(".status-filter"),
  setFilter: document.getElementById("set-filter"),
  listDensity: document.getElementById("list-density"),
  collapseList: document.getElementById("collapse-list"),
  showList: document.getElementById("show-list"),
  pdfFrame: document.getElementById("pdf-frame"),
  pdfTitle: document.getElementById("pdf-title"),
  pdfMeta: document.getElementById("pdf-meta"),
  mdMeta: document.getElementById("md-meta"),
  metadata: document.getElementById("metadata"),
  metadataSummary: document.getElementById("metadata-summary"),
  rawMd: document.getElementById("raw-md"),
  highlightMd: document.getElementById("highlight-md"),
  highlightCode: document.querySelector("#highlight-md code"),
  renderedMd: document.getElementById("rendered-md"),
  rawMode: document.getElementById("raw-mode"),
  highlightMode: document.getElementById("highlight-mode"),
  renderedMode: document.getElementById("rendered-mode"),
  zoomOut: document.getElementById("zoom-out"),
  zoomReset: document.getElementById("zoom-reset"),
  zoomIn: document.getElementById("zoom-in"),
  form: document.getElementById("annotation-form"),
  reviewStatus: document.getElementById("review-status"),
  page: document.getElementById("page"),
  location: document.getElementById("location"),
  comment: document.getElementById("comment"),
  clearNote: document.getElementById("clear-note"),
  saveStatus: document.getElementById("save-status"),
  annotationSummary: document.getElementById("annotation-summary"),
  exportReport: document.getElementById("export-report"),
};

const layoutStorageKey = "audit-decoder-layout-v1";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function loadLayout() {
  try {
    const saved = JSON.parse(localStorage.getItem(layoutStorageKey) || "{}");
    Object.assign(state.layout, saved);
  } catch {
    // Ignore invalid local layout state.
  }
  applyLayout();
  rebalanceContentWidths();
}

function saveLayout() {
  localStorage.setItem(layoutStorageKey, JSON.stringify(state.layout));
}

function applyLayout() {
  const { listWidth, pdfWidth, mdWidth, listCollapsed, mdZoom } = state.layout;
  el.shell.style.setProperty("--list-width", `${listWidth}px`);
  el.shell.style.setProperty("--pdf-width", `${pdfWidth}px`);
  el.shell.style.setProperty("--md-width", `${mdWidth}px`);
  el.shell.style.setProperty("--md-zoom", String(mdZoom));
  el.highlightMd.style.fontSize = `${0.85 * mdZoom}rem`;
  el.highlightCode.style.fontSize = "inherit";
  el.highlightCode.style.lineHeight = "inherit";
  el.shell.classList.toggle("list-collapsed", listCollapsed);
  el.showList.classList.toggle("hidden", !listCollapsed);
  el.zoomReset.textContent = `${Math.round(mdZoom * 100)}%`;
}

function availableContentWidth() {
  const shellWidth = el.shell.getBoundingClientRect().width;
  const handleWidth = state.layout.listCollapsed ? 5 : 10;
  const listWidth = state.layout.listCollapsed ? 0 : state.layout.listWidth;
  return Math.max(0, shellWidth - listWidth - handleWidth);
}

function rebalanceContentWidths() {
  const total = availableContentWidth();
  const current = state.layout.pdfWidth + state.layout.mdWidth;
  if (!total || !current) return;
  state.layout.pdfWidth = Math.round(total * (state.layout.pdfWidth / current));
  state.layout.mdWidth = Math.round(total - state.layout.pdfWidth);
  applyLayout();
}

function setListCollapsed(collapsed) {
  state.layout.listCollapsed = collapsed;
  rebalanceContentWidths();
  saveLayout();
}

function setZoom(nextZoom) {
  state.layout.mdZoom = clamp(nextZoom, 0.75, 1.6);
  applyLayout();
  saveLayout();
}

function beginResize(event) {
  const kind = event.currentTarget.dataset.resizer;
  const handle = event.currentTarget;
  handle.classList.add("dragging");
  handle.setPointerCapture(event.pointerId);

  const onMove = (moveEvent) => {
    const shellRect = el.shell.getBoundingClientRect();
    if (kind === "list") {
      const maxList = Math.min(520, shellRect.width * 0.42);
      state.layout.listWidth = Math.round(clamp(moveEvent.clientX - shellRect.left, 160, maxList));
      rebalanceContentWidths();
      return;
    }

    const listWidth = state.layout.listCollapsed ? 0 : state.layout.listWidth;
    const contentLeft = shellRect.left + listWidth + (state.layout.listCollapsed ? 0 : 5);
    const total = availableContentWidth();
    const pdfWidth = clamp(moveEvent.clientX - contentLeft, 300, Math.max(300, total - 300));
    state.layout.pdfWidth = Math.round(pdfWidth);
    state.layout.mdWidth = Math.round(total - pdfWidth);
    applyLayout();
  };

  const onDone = () => {
    handle.classList.remove("dragging");
    handle.removeEventListener("pointermove", onMove);
    handle.removeEventListener("pointerup", onDone);
    handle.removeEventListener("pointercancel", onDone);
    saveLayout();
  };

  handle.addEventListener("pointermove", onMove);
  handle.addEventListener("pointerup", onDone);
  handle.addEventListener("pointercancel", onDone);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function statusClass(doc) {
  if (doc.error_count > 0 || doc.status === "error") return "bad";
  if (doc.warning_count > 0 || doc.status === "warning") return "warn";
  return "";
}

function annotationStatus(docId) {
  const annotation = state.annotations[docId];
  return annotation?.review_status || "unvisited";
}

function annotationClass(docId) {
  const status = annotationStatus(docId);
  if (status === "unvisited") return "";
  return `note-${status}`;
}

function passesSetFilter(doc) {
  if (!state.setFilter) return true;
  return state.setMembership.get(state.setFilter)?.has(doc.doc_id) || false;
}

function passesStatusFilter(doc) {
  const status = annotationStatus(doc.doc_id);
  if (state.docFilter === "all") return true;
  if (state.docFilter === "unvisited") return status === "unvisited";
  if (state.docFilter === "annotated") return status !== "unvisited";
  return status === state.docFilter;
}

function matchesSearch(doc, query) {
  const haystack = [
    doc.doc_id,
    doc.title,
    doc.author_display,
    doc.year,
    doc.journal_label,
    doc.run_id,
  ].join(" ").toLowerCase();
  return haystack.includes(query);
}

function updateFilterCounts(searchMatchedDocs) {
  const counts = {
    all: searchMatchedDocs.length,
    unvisited: 0,
    annotated: 0,
    "needs-fix": 0,
  };
  for (const doc of searchMatchedDocs) {
    const status = annotationStatus(doc.doc_id);
    if (status === "unvisited") counts.unvisited += 1;
    if (status !== "unvisited") counts.annotated += 1;
    if (status === "needs-fix") counts["needs-fix"] += 1;
  }

  el.statusFilters.forEach((button) => {
    const status = button.dataset.filterStatus;
    const count = button.querySelector(".chip-count");
    if (count && status) count.textContent = String(counts[status] ?? 0);
  });
}

function renderDocList() {
  const query = el.filter.value.trim().toLowerCase();
  el.statusFilters.forEach((button) => {
    button.classList.toggle("active", button.dataset.filterStatus === state.docFilter);
  });
  el.docs.classList.toggle("compact", state.compactList);
  el.listDensity.textContent = state.compactList ? "Full" : "Lite";
  el.listDensity.title = state.compactList ? "Show full document rows" : "Show compact document rows";

  const searchMatchedDocs = state.docs.filter((doc) => matchesSearch(doc, query) && passesSetFilter(doc));
  updateFilterCounts(searchMatchedDocs);
  const docs = state.docs.filter((doc) => {
    return matchesSearch(doc, query) && passesSetFilter(doc) && passesStatusFilter(doc);
  });

  el.docCount.textContent = `${docs.length} of ${state.docs.length} documents`;
  el.docs.innerHTML = docs.map((doc) => {
    const active = doc.doc_id === state.currentDocId ? " active" : "";
    const noteStatus = annotationStatus(doc.doc_id);
    const marked = noteStatus !== "unvisited" ? " *" : "";
    const cls = statusClass(doc);
    const noteCls = annotationClass(doc.doc_id);
    const counts = `${doc.warning_count || 0}w/${doc.error_count || 0}e`;
    return `
      <div class="doc-item ${noteCls}${active}" data-doc-id="${escapeHtml(doc.doc_id)}" title="${escapeHtml(noteStatus)}" tabindex="0">
        <div class="doc-id ${cls}">${escapeHtml(doc.doc_id)}${marked}</div>
        <div class="doc-title">${escapeHtml(doc.title || "Untitled")}</div>
        <div class="doc-title">${escapeHtml(doc.status || "unknown")} · ${counts}</div>
      </div>
    `;
  }).join("");
}

function renderSetFilter() {
  const decodedIds = new Set(state.docs.map((doc) => doc.doc_id));
  const options = state.sets.map((set) => {
    const decodedCount = set.doc_ids.filter((docId) => decodedIds.has(docId)).length;
    return `<option value="${escapeHtml(set.name)}">${escapeHtml(set.name)} (${decodedCount}/${set.doc_ids.length})</option>`;
  });
  el.setFilter.innerHTML = `<option value="">All decode-lab sets</option>${options.join("")}`;
}

function markdownRenderer() {
  if (!window.markdownit) return null;
  return window.markdownit({
    html: false,
    linkify: true,
    typographer: false,
  });
}

function rewriteMarkdownMedia(markdown) {
  if (!state.currentDocId) return markdown;
  return markdown.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, url) => {
    if (/^(https?:|data:|\/)/.test(url)) return match;
    if (!url.startsWith("media/")) return match;
    const encoded = encodeURIComponent(url.slice("media/".length));
    return `![${alt}](/api/docs/${encodeURIComponent(state.currentDocId)}/media/${encoded})`;
  });
}

function stripInternalComments(markdown) {
  return markdown.replace(/<!--[\s\S]*?-->/g, "");
}

function renderMarkdown() {
  el.rawMd.textContent = state.currentMarkdown;
  if (window.Prism?.languages?.markdown) {
    el.highlightCode.innerHTML = window.Prism.highlight(
      state.currentMarkdown,
      window.Prism.languages.markdown,
      "markdown",
    );
  } else {
    el.highlightCode.textContent = state.currentMarkdown;
  }
  const renderer = markdownRenderer();
  if (!renderer) {
    el.renderedMd.innerHTML = `
      <p><strong>Rendered preview unavailable.</strong></p>
      <p>The CDN Markdown renderer did not load. Raw mode is still available.</p>
      <pre>${escapeHtml(state.currentMarkdown)}</pre>
    `;
    return;
  }

  const html = renderer.render(stripInternalComments(rewriteMarkdownMedia(state.currentMarkdown)));
  el.renderedMd.innerHTML = html;
  if (window.renderMathInElement) {
    window.renderMathInElement(el.renderedMd, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
        { left: "\\[", right: "\\]", display: true },
      ],
      throwOnError: false,
    });
  }
}

function setMode(mode) {
  state.mode = mode;
  el.rawMode.classList.toggle("active", mode === "raw");
  el.highlightMode.classList.toggle("active", mode === "highlight");
  el.renderedMode.classList.toggle("active", mode === "rendered");
  el.rawMd.classList.toggle("hidden", mode !== "raw");
  el.highlightMd.classList.toggle("hidden", mode !== "highlight");
  el.renderedMd.classList.toggle("hidden", mode !== "rendered");
  const modeText = {
    raw: "Raw is the audit source of truth.",
    highlight: "Highlighted raw Markdown; verify exact text in Raw.",
    rendered: "Rendered preview; verify audit decisions against Raw.",
  };
  el.mdMeta.textContent = modeText[mode] || modeText.raw;
}

function renderMetadata(payload) {
  const manifest = payload.manifest || {};
  const source = manifest.source || {};
  const quality = payload.quality || {};
  el.metadataSummary.textContent = [
    source.author_display,
    source.year,
    quality.status,
  ].filter(Boolean).join(" · ") || "No metadata.";
  const rows = [
    ["Title", source.title],
    ["Author", source.author_display],
    ["Year", source.year],
    ["Journal", source.journal_label],
    ["Run", manifest.run_id],
    ["Extractor", manifest.extractor],
    ["Quality", quality.status],
    ["Warnings", (quality.warnings || []).length],
    ["Errors", (quality.errors || []).length],
    ["Source URL", source.source_url],
  ];
  el.metadata.innerHTML = rows
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `<div class="meta-line"><strong>${escapeHtml(key)}:</strong> ${escapeHtml(value)}</div>`)
    .join("");
}

function fillAnnotation(annotation) {
  const item = annotation || {};
  el.reviewStatus.value = item.review_status || "unreviewed";
  el.page.value = item.page || "";
  el.location.value = item.location || "";
  el.comment.value = item.comment || "";
  el.saveStatus.textContent = item.updated_at ? `Saved ${item.updated_at}` : "";
  el.annotationSummary.textContent = item.updated_at
    ? `${item.review_status || "unreviewed"} · ${item.updated_at}`
    : "No note saved.";
}

async function loadDoc(docId) {
  state.currentDocId = docId;
  el.saveStatus.textContent = "";
  renderDocList();

  const [detailRes, markdownRes] = await Promise.all([
    fetch(`/api/docs/${encodeURIComponent(docId)}`),
    fetch(`/api/docs/${encodeURIComponent(docId)}/markdown`),
  ]);
  if (!detailRes.ok) throw new Error(await detailRes.text());
  if (!markdownRes.ok) throw new Error(await markdownRes.text());

  const detail = await detailRes.json();
  state.currentMarkdown = await markdownRes.text();
  state.annotations[docId] = detail.annotation || state.annotations[docId];

  const source = detail.manifest?.source || {};
  el.pdfTitle.textContent = source.title || docId;
  el.pdfMeta.textContent = [source.author_display, source.year, source.journal_label].filter(Boolean).join(" · ");
  el.pdfFrame.src = `/api/docs/${encodeURIComponent(docId)}/pdf`;
  renderMetadata(detail);
  renderMarkdown();
  fillAnnotation(detail.annotation);
}

async function saveAnnotation(event) {
  event.preventDefault();
  if (!state.currentDocId) return;
  el.saveStatus.textContent = "Saving...";
  const payload = {
    review_status: el.reviewStatus.value,
    page: el.page.value,
    location: el.location.value,
    comment: el.comment.value,
  };
  const res = await fetch(`/api/annotations/${encodeURIComponent(state.currentDocId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    el.saveStatus.textContent = "Save failed";
    return;
  }
  const data = await res.json();
  state.annotations[state.currentDocId] = data.annotation;
  el.saveStatus.textContent = `Saved ${data.annotation.updated_at}`;
  el.annotationSummary.textContent = `${data.annotation.review_status} · ${data.annotation.updated_at}`;
  renderDocList();
}

async function clearAnnotation() {
  if (!state.currentDocId) return;
  if (!state.annotations[state.currentDocId] && !el.comment.value.trim()) {
    fillAnnotation(null);
    return;
  }
  const ok = confirm("Clear the saved note for this document?");
  if (!ok) return;

  el.saveStatus.textContent = "Clearing...";
  const res = await fetch(`/api/annotations/${encodeURIComponent(state.currentDocId)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    el.saveStatus.textContent = "Clear failed";
    return;
  }
  delete state.annotations[state.currentDocId];
  fillAnnotation(null);
  el.saveStatus.textContent = "Cleared";
  renderDocList();
}

async function exportReport() {
  el.exportReport.textContent = "Exporting...";
  const res = await fetch("/api/export-markdown", { method: "POST" });
  if (!res.ok) {
    el.exportReport.textContent = "Export failed";
    return;
  }
  const data = await res.json();
  el.exportReport.textContent = "Export";
  alert(`Wrote ${data.path}`);
}

async function init() {
  loadLayout();
  const [docsRes, setsRes] = await Promise.all([
    fetch("/api/docs"),
    fetch("/api/sets"),
  ]);
  if (!docsRes.ok) throw new Error(await docsRes.text());
  const data = await docsRes.json();
  const setData = setsRes.ok ? await setsRes.json() : { sets: [] };
  state.docs = data.docs || [];
  state.sets = setData.sets || [];
  state.setMembership = new Map(state.sets.map((set) => [set.name, new Set(set.doc_ids)]));
  state.annotations = data.state?.annotations || {};
  renderSetFilter();
  renderDocList();
  const firstDoc = data.state?.last_doc_id || state.docs[0]?.doc_id;
  if (firstDoc) await loadDoc(firstDoc);
}

el.filter.addEventListener("input", renderDocList);
el.setFilter.addEventListener("change", () => {
  state.setFilter = el.setFilter.value;
  renderDocList();
});
el.statusFilters.forEach((button) => {
  button.addEventListener("click", () => {
    if (!button.dataset.filterStatus) return;
    state.docFilter = button.dataset.filterStatus;
    renderDocList();
  });
});
el.listDensity.addEventListener("click", () => {
  state.compactList = !state.compactList;
  renderDocList();
});
el.docs.addEventListener("click", (event) => {
  const item = event.target.closest(".doc-item");
  if (item) loadDoc(item.dataset.docId);
});
el.docs.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  const item = event.target.closest(".doc-item");
  if (item) loadDoc(item.dataset.docId);
});
el.rawMode.addEventListener("click", () => setMode("raw"));
el.highlightMode.addEventListener("click", () => setMode("highlight"));
el.renderedMode.addEventListener("click", () => setMode("rendered"));
el.zoomOut.addEventListener("click", () => setZoom(state.layout.mdZoom - 0.1));
el.zoomReset.addEventListener("click", () => setZoom(1));
el.zoomIn.addEventListener("click", () => setZoom(state.layout.mdZoom + 0.1));
el.collapseList.addEventListener("click", () => setListCollapsed(true));
el.showList.addEventListener("click", () => setListCollapsed(false));
document.querySelectorAll(".resize-handle").forEach((handle) => {
  handle.addEventListener("pointerdown", beginResize);
});
window.addEventListener("resize", () => {
  rebalanceContentWidths();
  saveLayout();
});
el.form.addEventListener("submit", saveAnnotation);
el.clearNote.addEventListener("click", clearAnnotation);
el.exportReport.addEventListener("click", exportReport);

init().catch((error) => {
  el.docCount.textContent = "Failed to load";
  el.docs.innerHTML = `<p class="bad">${escapeHtml(error.message)}</p>`;
});
