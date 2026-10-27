"""Resolve and fetch figures from release-pinned source Markdown."""

from __future__ import annotations

import posixpath
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


RAW_HOST = "raw.githubusercontent.com"
RAW_REPOSITORY = "cahcblr/sanchaya"
PAPERS_ROOT = "patra-darpan/papers"
MAX_FIGURE_BYTES = 2 * 1024 * 1024
FIGURE_TIMEOUT_SECONDS = 5
MAX_SOURCE_MARKDOWN_BYTES = 8 * 1024 * 1024

IMAGE_REFERENCE_RE = re.compile(
    r"!\[(?P<caption>(?:\\.|[^\]])*)\]\(\s*(?P<target><[^>]*>|[^)]*?)\s*\)",
    re.DOTALL,
)
FIGURE_NUMBER_RE = re.compile(r"\bFig(?:ure)?\.?\s*(\d+)\b", re.IGNORECASE)
FIGURE_META_RE = re.compile(r"<!--\s*figure-meta:\s*(.*?)\s*-->", re.IGNORECASE)
HIDDEN_PAGE_RENDER_RE = re.compile(
    r'<!--\s*figure-resolved-page-render-hidden:\s*image=(?P<image>.+?)\s+'
    r'caption="(?P<caption>.*?)"\s*-->',
    re.IGNORECASE,
)
EXTRACTED_FIGURE_RE = re.compile(
    r"<!--\s*figure-resolved-extracted:\s*page=(?P<page>\d+)\s+image=(?P<image>.*?)\s*-->",
    re.IGNORECASE,
)
META_FIELD_RE = re.compile(r"([a-z_-]+)\s*=\s*([^,]+)", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}\s+.+?\s*$")
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
BLOCK_RANGE_RE = re.compile(r"block:(\d+)-(\d+)")
TEXT_FIGURE_NUMBER_RE = re.compile(r"\b(?:Fig(?:ure)?\.?)\s*(\d+)\b", re.IGNORECASE)


def _decode_path(path: str) -> str:
    """Decode repeated URL escaping before checking for traversal."""
    for _ in range(8):
        decoded = urllib.parse.unquote(path)
        if decoded == path:
            return path
        path = decoded
    raise ValueError("figure path has excessive URL encoding")


def _paper_repo_path(path: str) -> str | None:
    if not path or "\\" in path or "\x00" in path or path.startswith("/"):
        return None
    normalized = posixpath.normpath(path)
    if normalized == PAPERS_ROOT or not normalized.startswith(PAPERS_ROOT + "/"):
        return None
    return normalized


def _encoded_repo_path(path: str) -> str:
    return "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))


def raw_url(corpus_revision: str, repo_path: str) -> str:
    safe_path = _paper_repo_path(repo_path)
    if safe_path is None or safe_path != repo_path:
        raise ValueError("figure path is outside patra-darpan/papers")
    revision = urllib.parse.quote(str(corpus_revision), safe="")
    return f"https://{RAW_HOST}/{RAW_REPOSITORY}/{revision}/{_encoded_repo_path(safe_path)}"


def _line_to_block(text: str) -> dict[int, int]:
    """Mirror retrieval_chunks.parse_blocks boundaries and retain line ordinals."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    linewise = not any(not line.strip() for line in lines[:-1])
    line_map: dict[int, int] = {}
    pending: list[int] = []
    pending_kind = "paragraph"
    ordinal = 0

    def flush() -> None:
        nonlocal pending, ordinal
        if pending:
            ordinal += 1
            for line_number in pending:
                line_map[line_number] = ordinal
        pending = []

    for line_number, line in enumerate(lines, start=1):
        if HEADING_RE.match(line):
            flush()
            continue
        is_table = bool(TABLE_RE.match(line))
        if not line.strip():
            flush()
            continue
        if pending and is_table != (pending_kind == "table"):
            flush()
        if linewise and pending and not is_table and pending_kind != "table":
            flush()
        pending_kind = "table" if is_table else "paragraph"
        pending.append(line_number)
        if linewise and not is_table:
            flush()
    flush()
    return line_map


def _parse_meta(lines: list[str], image_line: int) -> dict[str, str]:
    next_reference = next(
        (number for number in range(image_line + 1, len(lines) + 1)
         if IMAGE_REFERENCE_RE.search(lines[number - 1])
         or HIDDEN_PAGE_RENDER_RE.search(lines[number - 1])),
        len(lines) + 1,
    )
    next_heading = next(
        (number for number in range(image_line + 1, min(next_reference, len(lines) + 1))
         if HEADING_RE.match(lines[number - 1])),
        next_reference,
    )
    for line in lines[image_line:next_heading - 1]:
        match = FIGURE_META_RE.search(line)
        if not match:
            continue
        return {
            key.lower(): value.strip()
            for key, value in META_FIELD_RE.findall(match.group(1))
        }
    return {}


def _resolve_image_path(source_path: str, target: str) -> str | None:
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if not target:
        return None
    parsed = urllib.parse.urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith("//"):
        return None
    try:
        relative_path = _decode_path(parsed.path)
    except ValueError:
        return None
    if not relative_path or relative_path.startswith("/") or "\\" in relative_path or "\x00" in relative_path:
        return None
    resolved = _paper_repo_path(posixpath.join(posixpath.dirname(source_path), relative_path))
    return resolved


def figures_from_document(repo_path: str, markdown: str, corpus_revision: str) -> list[dict[str, Any]]:
    """Parse Markdown refs and resolved-image annotations at one release revision."""
    source_path = _paper_repo_path(repo_path)
    if source_path is None or posixpath.basename(source_path) != "document.md":
        return []

    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    line_blocks = _line_to_block(markdown)
    candidates: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        for match in IMAGE_REFERENCE_RE.finditer(line):
            resolved = _resolve_image_path(source_path, match.group("target"))
            if resolved is None:
                continue
            meta = _parse_meta(lines, line_number)
            caption = match.group("caption")
            fig_match = FIGURE_NUMBER_RE.search(caption)
            candidates.append({
                "caption": caption,
                "repo_path": resolved,
                "url": raw_url(corpus_revision, resolved),
                "page": int(meta["page"]) if meta.get("page", "").isdigit() else None,
                "type": meta.get("type"),
                "fig_no": int(fig_match.group(1)) if fig_match else None,
                "_source_line": line_number,
                "_source_block": line_blocks.get(line_number),
                "_image_kind": "markdown",
            })

        hidden = HIDDEN_PAGE_RENDER_RE.search(line)
        if hidden:
            resolved = _resolve_image_path(source_path, hidden.group("image"))
            caption = hidden.group("caption").strip()
            if resolved is not None:
                meta = _parse_meta(lines, line_number)
                fig_match = FIGURE_NUMBER_RE.search(caption)
                candidates.append({
                    "caption": caption,
                    "repo_path": resolved,
                    "url": raw_url(corpus_revision, resolved),
                    "page": int(meta["page"]) if meta.get("page", "").isdigit() else None,
                    "type": meta.get("type"),
                    "fig_no": int(fig_match.group(1)) if fig_match else None,
                    "_source_line": line_number,
                    "_source_block": line_blocks.get(line_number),
                    "_image_kind": "page-render",
                })

        extracted = EXTRACTED_FIGURE_RE.search(line)
        if extracted:
            resolved = _resolve_image_path(source_path, extracted.group("image"))
            if resolved is not None:
                previous = next(
                    (candidate for candidate in reversed(candidates)
                     if candidate.get("fig_no") is not None),
                    None,
                )
                if previous is not None:
                    meta = _parse_meta(lines, line_number)
                    candidates.append({
                        **previous,
                        "repo_path": resolved,
                        "url": raw_url(corpus_revision, resolved),
                        "page": int(extracted.group("page")),
                        "type": meta.get("type") or previous.get("type"),
                        "_image_kind": "extracted",
                    })

    # The same semantic figure can have both a page render and an extracted
    # crop. Keep the crop, retaining the original source span for chunk mapping.
    # Different figures may intentionally share one whole-page image.
    by_identity: dict[tuple[Any, ...], dict[str, Any]] = {}
    for candidate in candidates:
        fig_no = candidate.get("fig_no")
        identity = ("figure", fig_no) if fig_no is not None else (
            "image", candidate.get("repo_path"), candidate.get("caption"), candidate.get("page"),
        )
        current = by_identity.get(identity)
        if current is None:
            by_identity[identity] = candidate
            continue
        resolution_priority = {"markdown": 0, "page-render": 1, "extracted": 2}
        keep_candidate = (
            candidate if resolution_priority.get(str(candidate.get("_image_kind")), 0)
            > resolution_priority.get(str(current.get("_image_kind")), 0)
            else current
        )
        other = current if keep_candidate is candidate else candidate
        keep_candidate["_source_line"] = min(
            value for value in (current.get("_source_line"), candidate.get("_source_line"))
            if value is not None
        )
        keep_candidate["_source_block"] = (
            current.get("_source_block") if current.get("_source_block") is not None
            else candidate.get("_source_block")
        )
        if not keep_candidate.get("caption"):
            keep_candidate["caption"] = other.get("caption")
        if keep_candidate.get("page") is None:
            keep_candidate["page"] = other.get("page")
        if not keep_candidate.get("type"):
            keep_candidate["type"] = other.get("type")
        by_identity[identity] = keep_candidate

    return sorted(
        by_identity.values(),
        key=lambda item: (
            item["fig_no"] is None,
            item["fig_no"] if item["fig_no"] is not None else 0,
            item["repo_path"] or "",
        ),
    )


def figures_for_chunk(
    document_figures: list[dict[str, Any]], logical_location: str, chunk_text: str,
) -> list[dict[str, Any]]:
    """Attach figures by original chunk block span or a figure number in text."""
    span = BLOCK_RANGE_RE.search(str(logical_location or ""))
    block_start, block_end = (int(span.group(1)), int(span.group(2))) if span else (None, None)
    mentioned = {int(value) for value in TEXT_FIGURE_NUMBER_RE.findall(str(chunk_text or ""))}
    selected: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for figure in document_figures:
        fig_no = figure.get("fig_no")
        block_no = figure.get("_source_block")
        in_span = (
            block_no is not None and block_start is not None
            and block_start <= int(block_no) <= int(block_end)
        )
        if not in_span and (fig_no is None or fig_no not in mentioned):
            continue
        # Different figure captions can legitimately share one page render.
        # Keep those records distinct; identical figure/path pairs are duplicates.
        identity = (fig_no, str(figure.get("repo_path") or ""))
        if identity in seen:
            continue
        seen.add(identity)
        selected.append({
            key: figure.get(key)
            for key in ("caption", "repo_path", "url", "page", "type", "fig_no")
        })
    return sorted(
        selected,
        key=lambda item: (
            item["fig_no"] is None,
            item["fig_no"] if item["fig_no"] is not None else 0,
            item["repo_path"] or "",
        ),
    )


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def _read_bounded(url: str, *, timeout: int, max_bytes: int) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url, headers={"Accept": "image/*, text/markdown, text/plain", "User-Agent": "Sanchaya-Retrieval/1.0"},
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type().lower()
            length = response.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise ValueError(f"response exceeds {max_bytes} bytes")
            chunks: list[bytes] = []
            total = 0
            while True:
                block = response.read(min(64 * 1024, max_bytes + 1 - total))
                if not block:
                    break
                chunks.append(block)
                total += len(block)
                if total > max_bytes:
                    raise ValueError(f"response exceeds {max_bytes} bytes")
            return b"".join(chunks), content_type
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"source request returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(f"source request failed: {reason}") from exc


def fetch_document_markdown(repo_path: str, corpus_revision: str) -> str:
    safe_path = _paper_repo_path(repo_path)
    if safe_path is None or posixpath.basename(safe_path) != "document.md":
        raise ValueError("source document path is outside patra-darpan/papers")
    payload, _ = _read_bounded(
        raw_url(corpus_revision, safe_path),
        timeout=FIGURE_TIMEOUT_SECONDS,
        max_bytes=MAX_SOURCE_MARKDOWN_BYTES,
    )
    return payload.decode("utf-8")


def fetch_figure(figure: dict[str, Any], corpus_revision: str) -> tuple[bytes, str]:
    """Fetch one validated image with strict host, type, time and size bounds."""
    repo_path = str(figure.get("repo_path") or "")
    expected_url = raw_url(corpus_revision, repo_path)
    if figure.get("url") != expected_url:
        raise ValueError("figure URL does not match the pinned Sanchaya path")
    parsed = urllib.parse.urlsplit(expected_url)
    if parsed.scheme != "https" or parsed.hostname != RAW_HOST:
        raise ValueError("figure host is not allowed")
    data, content_type = _read_bounded(
        expected_url, timeout=FIGURE_TIMEOUT_SECONDS, max_bytes=MAX_FIGURE_BYTES,
    )
    if not content_type.startswith("image/"):
        raise ValueError(f"figure response is not an image ({content_type or 'unknown type'})")
    if not data:
        raise ValueError("figure response is empty")
    return data, content_type
