"""Dependency-free deterministic retrieval chunking.

The bakeoff deliberately keeps corpus inspection and chunking independent of
any embedding SDK.  This module is therefore usable from the local runner and
from unit tests without downloading a model or starting Qdrant.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


CHUNKER_VERSION = "retrieval-chunker.v1"
DEFAULT_TARGET_TOKENS = 384
DEFAULT_MAX_TOKENS = 480
DEFAULT_OVERLAP_TOKENS = 48

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
_TOKEN_RE = re.compile(r"\S+")


@dataclass(frozen=True)
class TextBlock:
    text: str
    heading_path: tuple[str, ...]
    kind: str
    ordinal: int


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tokenize(text: str) -> list[str]:
    """Return stable whitespace tokens for inventory and deterministic splits.

    These are intentionally only estimates.  Candidate model tokenizers are
    measured later, but using one stable tokenizer here keeps every candidate
    on identical chunk boundaries.
    """

    return _TOKEN_RE.findall(text.replace("\u00a0", " "))


def script_counts(text: str) -> dict[str, int]:
    counts = {"Devanagari": 0, "Latin": 0, "Other": 0}
    for char in text:
        if char.isspace() or unicodedata.category(char).startswith("M"):
            continue
        name = unicodedata.name(char, "")
        if "DEVANAGARI" in name:
            counts["Devanagari"] += 1
        elif "LATIN" in name or char.isascii() and char.isalpha():
            counts["Latin"] += 1
        else:
            counts["Other"] += 1
    return counts


def _heading_path_update(path: list[str], level: int, title: str) -> list[str]:
    del path[level - 1 :]
    path.append(title)
    return path


def parse_blocks(text: str) -> list[TextBlock]:
    """Parse Markdown/plain text into structure-aware blocks.

    Headings establish context but are retained in the next block's rendered
    embedding text.  Tables remain contiguous blocks so rows are not merged
    into an unrelated paragraph.  Plain text files simply use blank lines as
    boundaries.
    """

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # Many of the legacy Sanchaya plain-text files are verse/line oriented but
    # have no blank separators.  Treat each non-empty line as a block there so
    # a forced split does not arbitrarily cut a verse in half.  A terminal
    # newline is not itself a separator.
    linewise = not any(not line.strip() for line in lines[:-1])
    heading_path: list[str] = []
    blocks: list[TextBlock] = []
    pending: list[str] = []
    pending_kind = "paragraph"

    def flush() -> None:
        nonlocal pending
        rendered = "\n".join(pending).strip()
        if rendered:
            blocks.append(
                TextBlock(
                    text=rendered,
                    heading_path=tuple(heading_path),
                    kind=pending_kind,
                    ordinal=len(blocks) + 1,
                )
            )
        pending = []

    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            flush()
            _heading_path_update(heading_path, len(match.group(1)), match.group(2).strip())
            continue

        is_table = bool(_TABLE_RE.match(line))
        if not line.strip():
            flush()
            continue
        if pending and is_table != (pending_kind == "table"):
            flush()
        if linewise and pending and not is_table and pending_kind != "table":
            flush()
        pending_kind = "table" if is_table else "paragraph"
        pending.append(line.rstrip())
        if linewise and not is_table:
            flush()
    flush()
    return blocks


def _render_block(block: TextBlock) -> str:
    parts: list[str] = []
    if block.heading_path:
        parts.append("Heading: " + " > ".join(block.heading_path))
    parts.append(block.text)
    return "\n".join(parts)


def _split_long(text: str, max_tokens: int, overlap_tokens: int) -> Iterator[tuple[str, int]]:
    tokens = tokenize(text)
    if len(tokens) <= max_tokens:
        yield text.strip(), len(tokens)
        return
    start = 0
    part = 1
    step = max(1, max_tokens - overlap_tokens)
    while start < len(tokens):
        end = min(len(tokens), start + max_tokens)
        yield " ".join(tokens[start:end]), part
        if end == len(tokens):
            break
        start += step
        part += 1


def chunk_blocks(
    blocks: Iterable[TextBlock],
    *,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[dict[str, Any]]:
    """Pack blocks into deterministic chunks without crossing table boundaries."""

    if not (0 < target_tokens <= max_tokens):
        raise ValueError("target_tokens must be positive and no larger than max_tokens")
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be non-negative and smaller than max_tokens")

    result: list[dict[str, Any]] = []
    current: list[str] = []
    current_tokens = 0
    current_heading: tuple[str, ...] = ()
    current_kind = "paragraph"
    source_ordinals: list[int] = []

    def flush() -> None:
        nonlocal current, current_tokens, current_heading, current_kind, source_ordinals
        if not current:
            return
        result.append(
            {
                "text": "\n\n".join(current).strip(),
                "heading_path": list(current_heading),
                "kind": current_kind,
                "source_block_ordinals": list(source_ordinals),
                "forced_split": False,
            }
        )
        current = []
        current_tokens = 0
        current_heading = ()
        current_kind = "paragraph"
        source_ordinals = []

    for block in blocks:
        rendered = _render_block(block)
        block_tokens = tokenize(rendered)
        # A long block is split on the stable whitespace token stream.  It is
        # never packed with another block, and only this path uses overlap.
        if len(block_tokens) > max_tokens:
            flush()
            for part_text, part_number in _split_long(rendered, max_tokens, overlap_tokens):
                result.append(
                    {
                        "text": part_text,
                        "heading_path": list(block.heading_path),
                        "kind": block.kind,
                        "source_block_ordinals": [block.ordinal],
                        "forced_split": True,
                        "forced_split_part": part_number,
                    }
                )
            continue

        block_kind = block.kind
        cannot_merge = current and (block_kind == "table" or current_kind == "table")
        would_overflow = current_tokens + len(block_tokens) > max_tokens
        reached_target = current and current_tokens >= target_tokens
        if cannot_merge or would_overflow or reached_target:
            flush()
        if not current:
            current_heading = block.heading_path
            current_kind = block_kind
        current.append(rendered)
        source_ordinals.append(block.ordinal)
        current_tokens += len(block_tokens)
    flush()

    for item in result:
        item["token_estimate"] = len(tokenize(item["text"]))
    return result


def make_chunks_for_source(
    source: dict[str, Any],
    text: str,
    *,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[dict[str, Any]]:
    """Build stable, self-describing chunk records for one manifest source."""

    blocks = parse_blocks(text)
    packed = chunk_blocks(
        blocks,
        target_tokens=target_tokens,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )
    source_id = str(source["source_id"])
    document_id = str(source.get("document_id") or source_id)
    title = str(source.get("title") or "")
    repo_path = str(source["repo_path"])
    output: list[dict[str, Any]] = []
    for ordinal, item in enumerate(packed, start=1):
        body = str(item["text"])
        body_hash = sha256_bytes(body.encode("utf-8"))
        logical_location = f"block:{item['source_block_ordinals'][0]}-" \
            f"{item['source_block_ordinals'][-1]}:chunk:{ordinal}"
        stable_input = "|".join((source_id, logical_location, CHUNKER_VERSION, body_hash))
        chunk_id = f"retrieval:{hashlib.sha256(stable_input.encode('utf-8')).hexdigest()[:24]}"
        heading_path = list(item.get("heading_path") or [])
        embed_parts = [part for part in (title, " > ".join(heading_path), body) if part]
        output.append(
            {
                "schema_version": "retrieval.chunk.v1",
                "chunk_id": chunk_id,
                "source_id": source_id,
                "document_id": document_id,
                "source_kind": source.get("source_kind"),
                "repo_path": repo_path,
                "title": title,
                "heading_path": heading_path,
                "kind": item["kind"],
                "logical_location": logical_location,
                "chunker_version": CHUNKER_VERSION,
                "text": body,
                "embed_text": "\n".join(embed_parts),
                "token_estimate": int(item["token_estimate"]),
                "script_counts": script_counts(body),
                "content_sha256": body_hash,
                "forced_split": bool(item.get("forced_split", False)),
            }
        )
    return output
