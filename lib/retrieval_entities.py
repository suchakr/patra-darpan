"""Deterministic retrieval mention and entity-registry projections.

The first entity pass is intentionally conservative.  A curated ontology
supplies the vocabulary; this module finds explicit aliases in chunk/window
text and emits one auditable observation per match.  A mention is a graph edge
from a source window to an ontology entity.  The registry is a rebuildable node
projection, not an ontology editor and not a graph database.

Unknown entities are outside the scope of this gazetteer pass.  Ambiguous
aliases remain candidate links with a null canonical ID so later curation can
resolve them without changing the observed span.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


ENTITY_EXTRACTOR_VERSION = "starter-gazetteer-0.1.0"
MENTION_SCHEMA_VERSION = "retrieval.entity-mention.v1"
REGISTRY_SCHEMA_VERSION = "retrieval.entity-registry.v1"
BUILD_SCHEMA_VERSION = "retrieval.entity-build.v1"


@dataclass(frozen=True)
class AliasTarget:
    """One ontology entity associated with one normalized alias."""

    entity_id: str
    entity_type: str
    preferred_label: str
    alias: str
    normalized_alias: str


@dataclass(frozen=True)
class Match:
    """A match with offsets mapped back to the original window text."""

    alias: str
    normalized_alias: str
    start: int
    end: int
    surface: str
    targets: tuple[AliasTarget, ...]


@dataclass(frozen=True)
class NormalizedText:
    text: str
    # Each normalized code point maps to an original [start, end) span.
    spans: tuple[tuple[int, int], ...]


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Read JSONL objects without imposing a storage implementation."""

    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object at {path}:{line_number}")
            yield value


def ontology_version(ontology: dict[str, Any]) -> str:
    ontology_id = str(ontology.get("ontology_id") or "ontology")
    version = str(ontology.get("version") or "0")
    return f"{ontology_id}-{version}"


def _normalization_config(ontology: dict[str, Any]) -> dict[str, Any]:
    config = ontology.get("normalization")
    return config if isinstance(config, dict) else {}


def _normal_form(value: str, *, casefold: bool = True) -> str:
    """Normalize only what the pilot contract promises.

    We deliberately do not strip diacritics or punctuation.  Those changes can
    collapse distinct Sanskrit forms and should be introduced as explicit
    aliases after review.
    """

    normalized = unicodedata.normalize("NFC", value).replace("\u00a0", " ")
    return normalized.casefold() if casefold else normalized


def _clusters(value: str) -> Iterator[tuple[int, int, str]]:
    """Yield base-plus-combining-mark clusters for offset-safe normalization."""

    index = 0
    while index < len(value):
        end = index + 1
        while end < len(value) and unicodedata.category(value[end]).startswith("M"):
            end += 1
        yield index, end, value[index:end]
        index = end


def normalize_with_offsets(value: str, *, casefold: bool = True) -> NormalizedText:
    """Return a match string and map its code points to source offsets."""

    output: list[str] = []
    spans: list[tuple[int, int]] = []
    for start, end, cluster in _clusters(value):
        piece = unicodedata.normalize("NFC", cluster).replace("\u00a0", " ")
        if casefold:
            piece = piece.casefold()
        for char in piece:
            output.append(char)
            spans.append((start, end))
    return NormalizedText("".join(output), tuple(spans))


def _alias_pattern(alias: str) -> re.Pattern[str]:
    """Match explicit aliases while allowing whitespace across line breaks."""

    pieces = re.split(r"(\s+)", alias)
    pattern = "".join(r"\s+" if piece.isspace() else re.escape(piece) for piece in pieces if piece)
    return re.compile(pattern)


def _word_char(value: str) -> bool:
    return value == "_" or value.isalnum() or unicodedata.category(value).startswith("M")


def _has_boundaries(text: str, start: int, end: int) -> bool:
    """Require token-like boundaries for conservative alias matching."""

    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    return not (before and _word_char(before)) and not (after and _word_char(after))


def load_alias_targets(ontology: dict[str, Any]) -> tuple[dict[str, tuple[AliasTarget, ...]], dict[str, Any]]:
    """Validate a starter ontology and build normalized alias targets.

    The preferred label is included as an alias even when the JSON seed omits
    it.  Duplicate aliases are retained as a collision so the extractor can
    emit a candidate record instead of choosing a canonical ID arbitrarily.
    """

    entities = ontology.get("entities")
    if not isinstance(entities, list):
        raise ValueError("ontology.entities must be a list")
    config = _normalization_config(ontology)
    casefold = bool(config.get("latin_casefold", True))
    by_alias: dict[str, list[AliasTarget]] = defaultdict(list)
    seen_ids: set[str] = set()

    for raw in entities:
        if not isinstance(raw, dict):
            raise ValueError("every ontology entity must be an object")
        entity_id = str(raw.get("id") or "").strip()
        entity_type = str(raw.get("type") or "").strip()
        preferred = str(raw.get("preferred_label") or "").strip()
        if not entity_id or not entity_type or not preferred:
            raise ValueError("ontology entities require id, type, and preferred_label")
        if entity_id in seen_ids:
            raise ValueError(f"duplicate ontology entity id: {entity_id}")
        seen_ids.add(entity_id)
        raw_aliases = raw.get("aliases") or []
        if not isinstance(raw_aliases, list):
            raise ValueError(f"aliases must be a list for {entity_id}")
        aliases = [preferred, *(str(alias).strip() for alias in raw_aliases)]
        for alias in aliases:
            if not alias:
                continue
            normalized = _normal_form(alias, casefold=casefold)
            target = AliasTarget(entity_id, entity_type, preferred, alias, normalized)
            if target not in by_alias[normalized]:
                by_alias[normalized].append(target)

    targets = {key: tuple(value) for key, value in by_alias.items()}
    return targets, {"casefold": casefold, "entity_count": len(seen_ids), "alias_count": len(targets)}


def find_matches(text: str, alias_targets: dict[str, tuple[AliasTarget, ...]], *, casefold: bool = True) -> list[Match]:
    """Find explicit aliases and map match offsets into the original text."""

    normalized = normalize_with_offsets(text, casefold=casefold)
    matches: list[Match] = []
    # The starter vocabulary is small; one pass per explicit alias keeps the
    # implementation inspectable.  A trie/Aho-Corasick matcher can replace this
    # without changing the output contract when the vocabulary grows.
    for alias in sorted(alias_targets, key=lambda value: (-len(value), value)):
        pattern = _alias_pattern(alias)
        for found in pattern.finditer(normalized.text):
            start, end = found.span()
            if start == end or not _has_boundaries(normalized.text, start, end):
                continue
            original_start = normalized.spans[start][0]
            original_end = normalized.spans[end - 1][1]
            matches.append(
                Match(
                    alias=alias,
                    normalized_alias=alias,
                    start=original_start,
                    end=original_end,
                    surface=text[original_start:original_end],
                    targets=alias_targets[alias],
                )
            )

    # Multiple spelling aliases can produce the same observation.  Preserve
    # collisions, but avoid duplicate rows for the same entity and span.
    unique: dict[tuple[int, int, str, tuple[str, ...]], Match] = {}
    for match in matches:
        target_ids = tuple(sorted(target.entity_id for target in match.targets))
        key = (match.start, match.end, match.surface, target_ids)
        unique.setdefault(key, match)
    return sorted(unique.values(), key=lambda match: (match.start, match.end, match.alias))


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mention_id(
    *,
    corpus_revision: str,
    document_id: str,
    window_id: str,
    start: int,
    end: int,
    surface: str,
    ontology_version_value: str,
    target_ids: tuple[str, ...],
) -> str:
    stable = "|".join(
        (
            corpus_revision,
            document_id,
            window_id,
            str(start),
            str(end),
            surface,
            ontology_version_value,
            ",".join(target_ids),
        )
    )
    return "em:" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]


def mention_from_match(
    chunk: dict[str, Any],
    match: Match,
    *,
    corpus_revision: str,
    ontology_version_value: str,
) -> dict[str, Any]:
    """Convert one match into the versioned graph-edge observation."""

    target_ids = tuple(sorted(target.entity_id for target in match.targets))
    resolved = len(target_ids) == 1
    canonical_id = target_ids[0] if resolved else None
    entity_type = match.targets[0].entity_type if match.targets else None
    if len({target.entity_type for target in match.targets}) > 1:
        entity_type = None
    mention_id = _mention_id(
        corpus_revision=corpus_revision,
        document_id=str(chunk.get("document_id") or chunk.get("source_id") or ""),
        window_id=str(chunk.get("chunk_id") or ""),
        start=match.start,
        end=match.end,
        surface=match.surface,
        ontology_version_value=ontology_version_value,
        target_ids=target_ids,
    )
    window_text = str(chunk.get("text") or "")
    window: dict[str, Any] = {
        "id": str(chunk.get("chunk_id") or ""),
        "kind": str(chunk.get("kind") or "paragraph"),
        "section_path": list(chunk.get("heading_path") or []),
        "logical_location": str(chunk.get("logical_location") or ""),
        "text_sha256": str(chunk.get("content_sha256") or _text_hash(window_text)),
    }
    if chunk.get("page") is not None:
        window["page"] = chunk["page"]
    record: dict[str, Any] = {
        "schema_version": MENTION_SCHEMA_VERSION,
        "mention_id": mention_id,
        "corpus_revision": corpus_revision,
        "source_id": str(chunk.get("source_id") or ""),
        "document_id": str(chunk.get("document_id") or chunk.get("source_id") or ""),
        "repo_path": str(chunk.get("repo_path") or ""),
        "window": window,
        "span": {
            "start": match.start,
            "end": match.end,
            "unit": "unicode_codepoint",
            "basis": "window_text",
        },
        "surface_form": match.surface,
        "normalized_form": match.normalized_alias,
        "entity_type": entity_type,
        "canonical_entity_id": canonical_id,
        "candidate_entity_ids": list(target_ids) if not resolved else [],
        "resolution_status": "resolved" if resolved else "candidate",
        "confidence": 0.98 if resolved else 0.5,
        "extractor": {
            "name": "starter-gazetteer",
            "version": ENTITY_EXTRACTOR_VERSION,
            "method": "explicit_alias",
        },
        "ontology_version": ontology_version_value,
        "related_chunk_ids": [str(chunk.get("chunk_id") or "")],
    }
    return record


def iter_mentions(
    chunks: Iterable[dict[str, Any]],
    ontology: dict[str, Any],
    *,
    corpus_revision: str = "unknown",
) -> Iterator[dict[str, Any]]:
    """Yield deterministic mention edges for chunk/window records."""

    alias_targets, config = load_alias_targets(ontology)
    ontology_version_value = ontology_version(ontology)
    for chunk in chunks:
        text = str(chunk.get("text") or "")
        if not text or not chunk.get("chunk_id"):
            continue
        for match in find_matches(text, alias_targets, casefold=bool(config["casefold"])):
            yield mention_from_match(
                chunk,
                match,
                corpus_revision=corpus_revision,
                ontology_version_value=ontology_version_value,
            )


def registry_from_mentions(
    ontology: dict[str, Any], mentions: Iterable[dict[str, Any]], *, corpus_revision: str
) -> list[dict[str, Any]]:
    """Build a deterministic node/link projection from ontology plus mentions."""

    mention_rows = list(mentions)
    by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mention in mention_rows:
        entity_id = mention.get("canonical_entity_id")
        if entity_id:
            by_entity[str(entity_id)].append(mention)

    records: list[dict[str, Any]] = []
    for raw in ontology.get("entities") or []:
        if not isinstance(raw, dict):
            continue
        entity_id = str(raw.get("id") or "")
        rows = by_entity.get(entity_id, [])
        document_ids = sorted({str(row.get("document_id") or "") for row in rows if row.get("document_id")})
        chunk_ids = sorted(
            {
                str(chunk_id)
                for row in rows
                for chunk_id in row.get("related_chunk_ids") or []
                if chunk_id
            }
        )
        links = [
            {
                "mention_id": str(row["mention_id"]),
                "document_id": str(row["document_id"]),
                "chunk_id": str((row.get("related_chunk_ids") or [""])[0]),
                "repo_path": str(row.get("repo_path") or ""),
            }
            for row in rows
        ]
        records.append(
            {
                "schema_version": REGISTRY_SCHEMA_VERSION,
                "corpus_revision": corpus_revision,
                "ontology_version": ontology_version(ontology),
                "entity_id": entity_id,
                "entity_type": str(raw.get("type") or ""),
                "preferred_label": str(raw.get("preferred_label") or ""),
                "aliases": [str(alias) for alias in raw.get("aliases") or []],
                "status": "seed",
                "mention_count": len(rows),
                "document_count": len(document_ids),
                "document_ids": document_ids,
                "chunk_ids": chunk_ids,
                "links": links,
            }
        )
    return records


def build_summary(
    *,
    ontology: dict[str, Any],
    chunks_seen: int,
    mentions: list[dict[str, Any]],
    registry: list[dict[str, Any]],
    corpus_revision: str,
) -> dict[str, Any]:
    resolved = sum(row.get("resolution_status") == "resolved" for row in mentions)
    candidate = sum(row.get("resolution_status") == "candidate" for row in mentions)
    observed = sum(row.get("mention_count", 0) > 0 for row in registry)
    documents = {str(row.get("document_id")) for row in mentions if row.get("document_id")}
    return {
        "schema_version": BUILD_SCHEMA_VERSION,
        "extractor_version": ENTITY_EXTRACTOR_VERSION,
        "ontology_id": str(ontology.get("ontology_id") or ""),
        "ontology_version": ontology_version(ontology),
        "corpus_revision": corpus_revision,
        "chunks_seen": chunks_seen,
        "mention_count": len(mentions),
        "resolved_mention_count": resolved,
        "candidate_mention_count": candidate,
        "document_count_with_mentions": len(documents),
        "seed_entity_count": len(registry),
        "observed_entity_count": observed,
    }
