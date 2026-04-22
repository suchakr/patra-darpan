(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.SearchCore = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const STOPWORDS = new Set([
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "era",
  ]);

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function normalize(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }

  function tokenize(value) {
    const matches = normalize(value).match(/[\p{L}\p{N}\u0900-\u097F]+/gu) || [];
    return matches.filter((term) => term && !STOPWORDS.has(term));
  }

  function normalizedIndexMap(value) {
    const source = String(value || "");
    let normalized = "";
    const map = [];
    for (let i = 0; i < source.length; i += 1) {
      const folded = source[i].normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      for (let j = 0; j < folded.length; j += 1) {
        normalized += folded[j];
        map.push(i);
      }
    }
    return { normalized, map, source };
  }

  function headingText(chunk) {
    return Array.isArray(chunk.heading_path) ? chunk.heading_path.join(" > ") : "";
  }

  function searchableText(chunk) {
    return [
      chunk.title,
      chunk.author_display,
      chunk.year,
      headingText(chunk),
      chunk.doc_id,
      chunk.text,
    ]
      .filter(Boolean)
      .join(" ");
  }

  function termCount(haystack, needle) {
    if (!needle) return 0;
    let count = 0;
    let offset = 0;
    while (true) {
      const index = haystack.indexOf(needle, offset);
      if (index === -1) return count;
      count += 1;
      offset = index + needle.length;
    }
  }

  function scoreChunk(chunk, query) {
    const rawQuery = String(query || "").trim();
    const queryNorm = normalize(rawQuery);
    const terms = tokenize(rawQuery);
    if (!terms.length) return null;

    const fieldsNorm = normalize(searchableText(chunk));
    const textNorm = normalize(chunk.text);
    const titleNorm = normalize(chunk.title);
    const authorNorm = normalize(chunk.author_display);
    const headingNorm = normalize(headingText(chunk));

    let score = 0;
    if (queryNorm && fieldsNorm.includes(queryNorm)) score += 30;

    const uniqueTerms = Array.from(new Set(terms));
    let matchedTerms = 0;
    uniqueTerms.forEach((term) => {
      const count = termCount(fieldsNorm, term);
      if (!count) return;
      matchedTerms += 1;
      score += Math.min(count, 8) * 2;
      if (titleNorm.includes(term)) score += 8;
      if (headingNorm.includes(term)) score += 6;
      if (authorNorm.includes(term)) score += 4;
    });

    if (!matchedTerms) return null;
    if (matchedTerms > 1) score += matchedTerms * 3;
    score += Math.min(matchedTerms / uniqueTerms.length, 1) * 5;

    const snippet = makeSnippet(chunk.text || "", uniqueTerms);
    return {
      chunk,
      score,
      matched_terms: matchedTerms,
      terms: uniqueTerms,
      snippet,
      snippet_html: highlightSnippet(snippet, uniqueTerms),
    };
  }

  function makeSnippet(text, terms) {
    const source = String(text || "");
    const sourceNorm = normalize(source);
    let position = -1;
    const preferredTerms = Array.from(new Set(terms)).sort((a, b) => b.length - a.length);
    preferredTerms.forEach((term) => {
      const index = sourceNorm.indexOf(term);
      if (index !== -1 && position === -1) {
        position = index;
      }
    });
    if (position === -1) position = 0;

    const start = Math.max(0, position - 140);
    const end = Math.min(source.length, position + 340);
    let snippet = source.slice(start, end).trim();
    if (start > 0) snippet = "..." + snippet;
    if (end < source.length) snippet += "...";
    return snippet;
  }

  function highlightSnippet(snippet, terms) {
    return highlightText(snippet, terms);
  }

  function highlightText(text, terms) {
    const source = String(text || "");
    const normalizedTerms = Array.from(new Set((Array.isArray(terms) ? terms : tokenize(terms)).map(normalize).filter(Boolean)))
      .sort((a, b) => b.length - a.length);
    if (!source || !normalizedTerms.length) return escapeHtml(source);

    const { normalized, map } = normalizedIndexMap(source);
    const ranges = [];
    normalizedTerms.forEach((term) => {
      let offset = 0;
      while (offset < normalized.length) {
        const index = normalized.indexOf(term, offset);
        if (index === -1) break;
        const start = map[index];
        const end = (map[index + term.length - 1] ?? start) + 1;
        ranges.push([start, end]);
        offset = index + term.length;
      }
    });

    if (!ranges.length) return escapeHtml(source);
    ranges.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
    const merged = [];
    ranges.forEach((range) => {
      const last = merged[merged.length - 1];
      if (last && range[0] <= last[1]) {
        last[1] = Math.max(last[1], range[1]);
      } else {
        merged.push(range.slice());
      }
    });

    let html = "";
    let cursor = 0;
    merged.forEach(([start, end]) => {
      html += escapeHtml(source.slice(cursor, start));
      html += `<mark>${escapeHtml(source.slice(start, end))}</mark>`;
      cursor = end;
    });
    html += escapeHtml(source.slice(cursor));
    return html;
  }

  function compareResults(a, b) {
    if (b.score !== a.score) return b.score - a.score;
    const docCompare = String(a.chunk.doc_id || "").localeCompare(String(b.chunk.doc_id || ""));
    if (docCompare) return docCompare;
    return Number(a.chunk.chunk_ordinal || 0) - Number(b.chunk.chunk_ordinal || 0);
  }

  function buildChunkMap(corpus) {
    const map = new Map();
    (corpus && corpus.chunks ? corpus.chunks : []).forEach((chunk) => {
      map.set(chunk.chunk_id, chunk);
    });
    return map;
  }

  function search(corpus, query, options) {
    const limit = Number((options && options.limit) || 20);
    const chunks = corpus && Array.isArray(corpus.chunks) ? corpus.chunks : [];
    const results = [];
    chunks.forEach((chunk) => {
      const scored = scoreChunk(chunk, query);
      if (scored) results.push(scored);
    });
    results.sort(compareResults);
    return results.slice(0, limit);
  }

  function getNeighborHeadings(chunk, chunkMap) {
    const prev = chunk && chunk.prev_chunk_id ? chunkMap.get(chunk.prev_chunk_id) : null;
    const next = chunk && chunk.next_chunk_id ? chunkMap.get(chunk.next_chunk_id) : null;
    return {
      prev: prev ? { chunk_id: prev.chunk_id, heading: headingText(prev) } : null,
      next: next ? { chunk_id: next.chunk_id, heading: headingText(next) } : null,
    };
  }

  return {
    buildChunkMap,
    escapeHtml,
    getNeighborHeadings,
    headingText,
    highlightSnippet,
    highlightText,
    scoreChunk,
    search,
    tokenize,
  };
});
