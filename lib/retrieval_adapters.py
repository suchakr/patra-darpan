"""Read-only adapters for the three retrieval projections.

The MCP layer calls these adapters rather than knowing whether a projection is
served by Zoekt, Qdrant, or JSONL.  Every adapter is deliberately read-only;
build jobs produce the release artifacts and the online process only opens
them.  Optional heavy dependencies are imported only when their backend is
used so entity lookup and passage fetch remain lightweight.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
import base64
import binascii
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urljoin

import requests


class RetrievalError(RuntimeError):
    """A bounded, user-safe retrieval failure."""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetrievalError(f"cannot read JSON artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RetrievalError(f"JSON artifact is not an object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        handle = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise RetrievalError(f"cannot read JSONL artifact {path}: {exc}") from exc
    with handle:
        for line_no, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RetrievalError(f"invalid JSON at {path}:{line_no}: {exc}") from exc
            if not isinstance(value, dict):
                raise RetrievalError(f"expected an object at {path}:{line_no}")
            rows.append(value)
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(root: Path, value: str) -> Path:
    """Resolve a release artifact without allowing path traversal."""

    candidate = Path(value)
    if candidate.is_absolute() or "\\" in value:
        raise RetrievalError(f"artifact path must be relative: {value!r}")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise RetrievalError(f"artifact path escapes release root: {value!r}") from exc
    return resolved


@dataclass(frozen=True)
class Release:
    """One immutable release record and its release-root-relative artifacts."""

    path: Path
    record: dict[str, Any]

    @property
    def root(self) -> Path:
        return self.path.parent

    @property
    def release_id(self) -> str:
        return str(self.record.get("release_id") or "unknown")

    @property
    def corpus_revision(self) -> str:
        return str(self.record.get("source", {}).get("sanchaya_commit") or "unknown")

    def artifact_path(self, name: str) -> Path:
        artifacts = self.record.get("artifacts")
        if not isinstance(artifacts, dict) or not isinstance(artifacts.get(name), dict):
            raise RetrievalError(f"release does not declare artifact {name!r}")
        value = artifacts[name].get("path")
        if not isinstance(value, str) or not value:
            raise RetrievalError(f"release artifact {name!r} has no path")
        path = _safe_relative(self.root, value)
        if not path.is_file():
            raise RetrievalError(f"release artifact is missing: {path}")
        return path

    def artifact_hash(self, name: str) -> str | None:
        artifacts = self.record.get("artifacts")
        if not isinstance(artifacts, dict) or not isinstance(artifacts.get(name), dict):
            return None
        value = artifacts[name].get("sha256")
        return str(value) if value else None


def load_release(path: str | Path | None = None) -> Release:
    configured = path or os.getenv("RETRIEVAL_ACTIVE_RELEASE")
    if not configured:
        root = Path(os.getenv("RETRIEVAL_RELEASE_ROOT", ".local/retrieval/releases"))
        configured = root / "active-release.json"
    release_path = Path(configured).expanduser().resolve()
    record = read_json(release_path)
    if record.get("schema_version") != "retrieval.release.v1":
        raise RetrievalError(f"unsupported release schema in {release_path}")
    if record.get("status") != "ready":
        raise RetrievalError(f"release is not ready: {record.get('status')!r}")
    release = Release(release_path, record)
    # Verify file artifacts before exposing them through MCP.  Backend
    # identifiers (Zoekt/Qdrant) are checked when their adapter connects.
    artifacts = record.get("artifacts") or {}
    for name, descriptor in artifacts.items():
        if not isinstance(descriptor, dict) or "path" not in descriptor:
            continue
        artifact_path = release.artifact_path(str(name))
        expected = descriptor.get("sha256")
        if expected and sha256_file(artifact_path) != str(expected):
            raise RetrievalError(f"release artifact hash mismatch: {name}")
    return release


def _normal_form(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\u00a0", " ").casefold()


class EntityAdapter:
    """Lookup and mention browsing over the release JSONL projections."""

    def __init__(self, release: Release, ontology_path: str | Path):
        self.release = release
        self.ontology_path = Path(ontology_path).expanduser().resolve()
        self.ontology = read_json(self.ontology_path)
        self.registry = read_jsonl(release.artifact_path("entity_registry"))
        self.mentions = read_jsonl(release.artifact_path("entity_mentions"))
        expected_ontology = release.record.get("pipeline", {}).get("ontology", {})
        if expected_ontology:
            actual_id = str(self.ontology.get("ontology_id") or "")
            actual_version = str(self.ontology.get("version") or "")
            if actual_id != str(expected_ontology.get("id") or "") or actual_version != str(expected_ontology.get("version") or ""):
                raise RetrievalError(
                    "ontology does not match active release: "
                    f"expected {expected_ontology.get('id')} {expected_ontology.get('version')}, "
                    f"found {actual_id} {actual_version}"
                )
        for row in (*self.registry, *self.mentions):
            revision = row.get("corpus_revision")
            if revision and str(revision) != release.corpus_revision:
                raise RetrievalError("entity projection corpus revision does not match active release")
        self._by_id = {str(row.get("entity_id")): row for row in self.registry if row.get("entity_id")}
        self._mentions_by_id: dict[str, list[dict[str, Any]]] = {}
        for row in self.mentions:
            entity_id = row.get("canonical_entity_id")
            if entity_id:
                self._mentions_by_id.setdefault(str(entity_id), []).append(row)
        self._aliases: list[tuple[str, str, str]] = []
        for row in self.registry:
            entity_id = str(row.get("entity_id") or "")
            if not entity_id:
                continue
            labels = [row.get("preferred_label"), *(row.get("aliases") or [])]
            for label in labels:
                if label:
                    self._aliases.append((str(label), _normal_form(str(label)), entity_id))

    @property
    def ontology_context(self) -> dict[str, Any]:
        entities = self.ontology.get("entities") or []
        compact_entities = []
        for row in entities:
            if not isinstance(row, dict):
                continue
            compact_entities.append(
                {
                    "id": row.get("id"),
                    "type": row.get("type"),
                    "preferred_label": row.get("preferred_label"),
                    "aliases": list(row.get("aliases") or []),
                }
            )
        return {
            "schema_version": "retrieval.ontology-context.v1",
            "ontology_id": self.ontology.get("ontology_id"),
            "version": self.ontology.get("version"),
            "normalization": self.ontology.get("normalization", {}),
            "entity_types": self.ontology.get("entity_types", []),
            "relation_types": self.ontology.get("relation_types", []),
            "entities": compact_entities,
            "corpus_revision": self.release.corpus_revision,
        }

    def lookup(self, name: str, *, type_hint: str | None = None, limit: int = 10) -> dict[str, Any]:
        query = _normal_form(name.strip())
        if not query:
            raise RetrievalError("name must not be empty")
        limit = max(1, min(int(limit), 50))
        ranked: list[tuple[int, str, str]] = []
        for label, normalized, entity_id in self._aliases:
            rank = 0 if normalized == query else (1 if normalized.startswith(query) else 2 if query in normalized else 99)
            if rank >= 99:
                continue
            row = self._by_id.get(entity_id, {})
            if type_hint and str(row.get("entity_type") or "") != type_hint:
                continue
            ranked.append((rank, label, entity_id))
        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for rank, matched_label, entity_id in sorted(ranked, key=lambda item: (item[0], item[2], item[1])):
            if entity_id in seen:
                continue
            seen.add(entity_id)
            source = self._by_id.get(entity_id) or {}
            document_ids = [str(value) for value in source.get("document_ids") or [] if value]
            row = {
                "entity_id": entity_id,
                "entity_type": source.get("entity_type"),
                "preferred_label": source.get("preferred_label"),
                "aliases": list(source.get("aliases") or []),
                "status": source.get("status"),
                "mention_count": int(source.get("mention_count") or 0),
                "document_count": int(source.get("document_count") or len(document_ids)),
                "document_ids": document_ids[:25],
                "document_ids_truncated": len(document_ids) > 25,
                "matched_label": matched_label,
                "match_rank": rank,
            }
            results.append(row)
            if len(results) >= limit:
                break
        return {
            "schema_version": "retrieval.entity-lookup.v1",
            "query": name,
            "type_hint": type_hint,
            "results": results,
            "corpus_revision": self.release.corpus_revision,
        }

    def list_mentions(self, entity_id: str, *, offset: int = 0, limit: int = 20) -> dict[str, Any]:
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        if entity_id not in self._by_id:
            raise RetrievalError(f"unknown entity ID: {entity_id}")
        rows = self._mentions_by_id.get(entity_id, [])
        return {
            "schema_version": "retrieval.entity-mentions.v1",
            "entity_id": entity_id,
            "total": len(rows),
            "offset": offset,
            "limit": limit,
            "mentions": rows[offset : offset + limit],
            "corpus_revision": self.release.corpus_revision,
        }

    def chunk_ids_for(self, entity_ids: Iterable[str]) -> set[str]:
        wanted = {str(value) for value in entity_ids if value}
        result: set[str] = set()
        for entity_id in wanted:
            row = self._by_id.get(entity_id)
            if row:
                result.update(str(value) for value in row.get("chunk_ids") or [] if value)
        return result

    def document_ids_for(self, entity_ids: Iterable[str]) -> set[str]:
        wanted = {str(value) for value in entity_ids if value}
        result: set[str] = set()
        for entity_id in wanted:
            row = self._by_id.get(entity_id)
            if row:
                result.update(str(value) for value in row.get("document_ids") or [] if value)
        return result


IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


class PassageStore:
    """Bounded passage lookup over the chunk projection plus corpus metadata."""

    def __init__(self, release: Release):
        self.release = release
        self.chunks = read_jsonl(release.artifact_path("chunks"))
        self.by_id = {str(row.get("chunk_id")): row for row in self.chunks if row.get("chunk_id")}
        self.by_repo_path: dict[str, list[dict[str, Any]]] = {}
        self.by_document: dict[str, list[dict[str, Any]]] = {}
        for row in self.chunks:
            if row.get("repo_path"):
                self.by_repo_path.setdefault(str(row["repo_path"]), []).append(row)
            if row.get("document_id"):
                self.by_document.setdefault(str(row["document_id"]), []).append(row)

        self.catalog: dict[str, dict[str, Any]] = {}
        try:
            catalog_rows = read_jsonl(release.artifact_path("corpus_manifest"))
        except RetrievalError:
            catalog_rows = []
        for row in catalog_rows:
            for key in (row.get("document_id"), row.get("source_doc_id")):
                if key:
                    self.catalog[str(key)] = row

    def _media(self, chunk: dict[str, Any]) -> list[dict[str, str]]:
        repo_path = PurePosixPath(str(chunk.get("repo_path") or ""))
        result: list[dict[str, str]] = []
        for target in IMAGE_RE.findall(str(chunk.get("text") or "")):
            target = target.split("#", 1)[0].split("?", 1)[0].strip()
            if not target or target.startswith(("/", "//")) or ":" in target.split("/", 1)[0]:
                continue
            media_path = PurePosixPath(repo_path.parent, target)
            if ".." in media_path.parts:
                continue
            result.append({"path": str(media_path), "target": target})
        return result

    def _format(self, chunk: dict[str, Any], *, lexical: dict[str, Any] | None = None) -> dict[str, Any]:
        document_id = str(chunk.get("document_id") or "")
        catalog = self.catalog.get(document_id, {})
        result = {
            "chunk_id": chunk.get("chunk_id"),
            "document_id": document_id,
            "source_id": chunk.get("source_id"),
            "source_kind": chunk.get("source_kind"),
            "repo_path": chunk.get("repo_path"),
            "title": chunk.get("title") or catalog.get("title"),
            "heading_path": chunk.get("heading_path", []),
            "kind": chunk.get("kind"),
            "logical_location": chunk.get("logical_location"),
            "text": chunk.get("text"),
            "content_sha256": chunk.get("content_sha256"),
            "corpus_revision": self.release.corpus_revision,
            "source_refs": catalog.get("source_refs", []),
            "media": self._media(chunk),
        }
        if catalog.get("authors") is not None:
            result["authors"] = catalog["authors"]
        if catalog.get("year") is not None:
            result["year"] = catalog["year"]
        if lexical:
            result["lexical_match"] = lexical
        return result

    def fetch(
        self,
        *,
        chunk_id: str | None = None,
        document_id: str | None = None,
        repo_path: str | None = None,
        limit: int = 5,
        lexical: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 20))
        if chunk_id:
            row = self.by_id.get(chunk_id)
            if row is None:
                raise RetrievalError(f"unknown chunk ID: {chunk_id}")
            rows = [row]
        elif document_id:
            rows = self.by_document.get(document_id, [])[:limit]
        elif repo_path:
            rows = self.by_repo_path.get(repo_path, [])[:limit]
        else:
            raise RetrievalError("one of chunk_id, document_id, or repo_path is required")
        return {
            "schema_version": "retrieval.passage.v1",
            "requested": {"chunk_id": chunk_id, "document_id": document_id, "repo_path": repo_path},
            "passages": [self._format(row, lexical=lexical if index == 0 else None) for index, row in enumerate(rows)],
            "corpus_revision": self.release.corpus_revision,
        }


class ZoektAdapter:
    """Small client for Zoekt's read-only JSON RPC endpoint."""

    def __init__(self, url: str | None = None, *, timeout: float = 10.0):
        self.url = (url or os.getenv("ZOEKT_URL") or os.getenv("RETRIEVAL_ZOEKT_URL") or "").rstrip("/")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def search(self, query: str, *, limit: int = 10, context_lines: int = 2) -> list[dict[str, Any]]:
        if not self.url:
            return []
        if not query.strip():
            raise RetrievalError("query must not be empty")
        limit = max(1, min(int(limit), 50))
        context_lines = max(0, min(int(context_lines), 10))
        # Catalog and entity JSONL paths are metadata, not the user-facing
        # lexical corpus.  The exclusion is part of the adapter boundary.
        protected_query = f"({query}) -file:patra-darpan/catalog/ -file:ontology/"
        payload = {
            "Q": protected_query,
            "Opts": {
                "MaxDocDisplayCount": limit,
                "MaxMatchDisplayCount": limit * 5,
                "NumContextLines": context_lines,
            },
        }
        try:
            response = requests.post(
                urljoin(self.url + "/", "api/search"),
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RetrievalError(f"Zoekt search failed: {exc}") from exc
        result = body.get("Result") or body.get("result") or {}
        files = result.get("Files") or result.get("FileMatches") or result.get("file_matches") or []
        output: list[dict[str, Any]] = []
        for file_match in files[:limit]:
            if not isinstance(file_match, dict):
                continue
            # The JSON API uses Go's exported field names (Repository,
            # LineMatches, ...), while older deployments and test doubles may
            # use the shorter web-template names.  Normalize both here.
            matches = file_match.get("LineMatches")
            if matches is None:
                matches = file_match.get("Matches", file_match.get("matches", []))
            matches = [self._normalize_match(match) for match in matches if isinstance(match, dict)]
            output.append(
                {
                    "backend": "zoekt",
                    "score": file_match.get("Score", file_match.get("score")),
                    "repo": file_match.get(
                        "Repository",
                        file_match.get("Repo", file_match.get("repo")),
                    ),
                    "repo_path": file_match.get("FileName", file_match.get("file_name")),
                    "url": file_match.get("URL", file_match.get("url")),
                    "matches": matches,
                    "branches": file_match.get("Branches", file_match.get("branches", [])),
                }
            )
        return output

    @staticmethod
    def _decode(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        try:
            decoded = base64.b64decode(value, validate=True)
            return decoded.decode("utf-8")
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return value

    @classmethod
    def _normalize_match(cls, match: dict[str, Any]) -> dict[str, Any]:
        """Turn Zoekt's base64 encoded byte fields into MCP-friendly text."""

        fragments = match.get("LineFragments") or match.get("fragments") or []
        return {
            "line_number": match.get("LineNumber", match.get("line_number")),
            "line": cls._decode(match.get("Line", match.get("line"))),
            "before": cls._decode(match.get("Before", match.get("before"))),
            "after": cls._decode(match.get("After", match.get("after"))),
            "fragments": fragments,
        }


class VectorAdapter:
    """Query adapter for the Qdrant collection named by the active release."""

    def __init__(self, release: Release, *, qdrant_url: str | None = None, model_name: str | None = None):
        self.release = release
        vector = release.record.get("artifacts", {}).get("vector_index", {})
        pipeline = release.record.get("pipeline", {}).get("embedding", {})
        self.collection = str(vector.get("collection") or os.getenv("RETRIEVAL_QDRANT_COLLECTION") or "")
        self.model_name = model_name or os.getenv("RETRIEVAL_EMBEDDING_MODEL") or str(pipeline.get("model") or "")
        self.qdrant_url = qdrant_url or os.getenv("QDRANT_URL") or os.getenv("RETRIEVAL_QDRANT_URL") or "http://127.0.0.1:6333"
        self.device = os.getenv("RETRIEVAL_EMBEDDING_DEVICE") or None
        self._model: Any = None
        self._client: Any = None

    def _load(self) -> tuple[Any, Any]:
        if self._model is None or self._client is None:
            if not self.collection or not self.model_name:
                raise RetrievalError("release does not configure a vector collection and model")
            try:
                from qdrant_client import QdrantClient
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RetrievalError("vector search needs qdrant-client and sentence-transformers") from exc
            try:
                self._client = QdrantClient(url=self.qdrant_url)
                self._model = SentenceTransformer(self.model_name, device=self.device)
            except Exception as exc:  # SDK errors vary by version/backend.
                raise RetrievalError(f"cannot initialize vector backend: {exc}") from exc
        return self._client, self._model

    def search(self, query: str, *, limit: int = 10, allowed_chunk_ids: set[str] | None = None) -> list[dict[str, Any]]:
        if not query.strip():
            raise RetrievalError("query must not be empty")
        client, model = self._load()
        limit = max(1, min(int(limit), 50))
        text = f"query: {query}" if "e5" in self.model_name.lower() else query
        try:
            vector = model.encode([text], normalize_embeddings=True, convert_to_numpy=True)[0].tolist()
            # Ask for extra candidates when an entity filter is applied; the
            # release remains read-only and the post-filter is deterministic.
            probe_limit = min(100, max(limit, limit * 5)) if allowed_chunk_ids else limit
            if hasattr(client, "query_points"):
                response = client.query_points(
                    collection_name=self.collection,
                    query=vector,
                    limit=probe_limit,
                    with_payload=True,
                )
                points = getattr(response, "points", response)
            else:  # qdrant-client < 1.14 compatibility
                points = client.search(
                    collection_name=self.collection,
                    query_vector=vector,
                    limit=probe_limit,
                    with_payload=True,
                )
        except Exception as exc:
            raise RetrievalError(f"vector search failed: {exc}") from exc
        output: list[dict[str, Any]] = []
        for point in points:
            payload = getattr(point, "payload", None) or (point.get("payload", {}) if isinstance(point, dict) else {})
            payload = dict(payload)
            chunk_id = str(payload.get("chunk_id") or "")
            if allowed_chunk_ids is not None and chunk_id not in allowed_chunk_ids:
                continue
            score = getattr(point, "score", None)
            if score is None and isinstance(point, dict):
                score = point.get("score")
            output.append(
                {
                    "backend": "vector",
                    "score": score,
                    "chunk_id": chunk_id,
                    **payload,
                }
            )
            if len(output) >= limit:
                break
        return output


def reciprocal_rank_fusion(groups: Iterable[Iterable[dict[str, Any]]], *, limit: int) -> list[dict[str, Any]]:
    """Fuse lexical and vector rows using a transparent rank-only score."""

    by_key: dict[str, dict[str, Any]] = {}
    scores: dict[str, float] = {}
    for group in groups:
        for rank, row in enumerate(group, start=1):
            key = str(row.get("chunk_id") or row.get("repo_path") or row.get("url") or "")
            if not key:
                continue
            scores[key] = scores.get(key, 0.0) + 1.0 / (60.0 + rank)
            by_key.setdefault(key, dict(row))
    output = []
    for key, row in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]:
        result = by_key[key]
        result["fusion_score"] = round(row, 6)
        result["backend"] = "hybrid"
        output.append(result)
    return output


class RetrievalService:
    """Composition root used by MCP and direct local smoke calls."""

    def __init__(self, release: Release, *, ontology_path: str | Path, zoekt_url: str | None = None, qdrant_url: str | None = None):
        self.release = release
        self.entities = EntityAdapter(release, ontology_path)
        self.passages = PassageStore(release)
        self.zoekt = ZoektAdapter(zoekt_url)
        self.vector = VectorAdapter(release, qdrant_url=qdrant_url)

    def search(
        self,
        query: str,
        *,
        mode: str = "hybrid",
        limit: int = 10,
        entity_ids: Iterable[str] = (),
    ) -> dict[str, Any]:
        mode = mode.lower().strip()
        if mode not in {"lexical", "vector", "hybrid"}:
            raise RetrievalError("mode must be lexical, vector, or hybrid")
        limit = max(1, min(int(limit), 50))
        entity_ids = list(entity_ids)
        allowed = self.entities.chunk_ids_for(entity_ids)
        allowed_documents = self.entities.document_ids_for(entity_ids)
        backend_errors: dict[str, str] = {}
        lexical: list[dict[str, Any]] = []
        vector: list[dict[str, Any]] = []
        if mode in {"lexical", "hybrid"}:
            try:
                lexical = self.zoekt.search(query, limit=limit)
                if entity_ids:
                    lexical = [
                        row
                        for row in lexical
                        if any(
                            str(chunk.get("document_id")) in allowed_documents
                            for chunk in self.passages.by_repo_path.get(str(row.get("repo_path") or ""), [])
                        )
                    ]
            except RetrievalError as exc:
                backend_errors["lexical"] = str(exc)
        if mode in {"vector", "hybrid"}:
            try:
                vector = self.vector.search(
                    query,
                    limit=limit,
                    allowed_chunk_ids=allowed if entity_ids else None,
                )
            except RetrievalError as exc:
                backend_errors["vector"] = str(exc)
        if mode == "lexical":
            results = lexical
        elif mode == "vector":
            results = vector
        else:
            results = reciprocal_rank_fusion((lexical, vector), limit=limit)
        return {
            "schema_version": "retrieval.search.v1",
            "query": query,
            "mode": mode,
            "entity_ids": list(entity_ids),
            "results": results,
            "backend_counts": {"lexical": len(lexical), "vector": len(vector)},
            "backend_errors": backend_errors,
            "corpus_revision": self.release.corpus_revision,
            "release_id": self.release.release_id,
        }
