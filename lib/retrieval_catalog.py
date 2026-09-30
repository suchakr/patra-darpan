"""Composite, read-only document catalog for retrieval releases.

Patra Darpan's canonical SQLite database is authoritative for ``pd:*``
documents.  Sanchaya text files are described by the release input manifest.
This module materializes both authorities into one immutable release catalog so
the online MCP process has one bounded metadata interface without pretending
that the two upstream sources are the same database.
"""

from __future__ import annotations

import json
import hashlib
import re
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


CATALOG_SCHEMA_VERSION = "retrieval.catalog.v2"


class CatalogError(RuntimeError):
    """A safe, user-facing catalog error."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


CATALOG_SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA user_version = 2;

CREATE TABLE catalog_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_doc_id TEXT,
    title TEXT,
    authors_json TEXT NOT NULL,
    year TEXT,
    journal TEXT,
    categories_json TEXT NOT NULL,
    repo_path TEXT,
    source_refs_json TEXT NOT NULL,
    content_sha256 TEXT,
    indexed_in_release INTEGER NOT NULL DEFAULT 0 CHECK (indexed_in_release IN (0, 1)),
    metadata_status TEXT NOT NULL,
    authority TEXT NOT NULL
);

CREATE INDEX documents_source_kind_idx ON documents(source_kind);
CREATE INDEX documents_year_idx ON documents(year);
CREATE INDEX documents_repo_path_idx ON documents(repo_path);
"""


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return default
        return parsed
    return value


def _json_list(value: Any) -> list[Any]:
    parsed = _json_value(value, value)
    if isinstance(parsed, list):
        return parsed
    if parsed in (None, ""):
        return []
    return [parsed]


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _author_key(value: Any) -> str:
    """Normalize punctuation and diacritics for author lookup.

    The catalog keeps the display spelling supplied by the source.  Lookup
    needs a tolerant comparison so ``R. N. Iyengar`` and ``R N Iyengar`` do
    not send the chat host into a punctuation-variant search loop.
    """

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _document_id(value: Any, source_kind: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise CatalogError(f"catalog row has no document ID ({source_kind})")
    if raw.startswith("pd:") or raw.startswith("sanchaya:"):
        return raw
    return f"{'pd' if source_kind == 'patra-darpan' else 'sanchaya'}:{raw}"


def _source_kind(value: Any, *, fallback: str = "sanchaya") -> str:
    raw = str(value or "").strip().lower()
    if raw in {"pd", "patra-darpan", "patra_darpan", "paper"}:
        return "patra-darpan"
    if raw in {"sanchaya", "text", "source"}:
        return "sanchaya"
    return fallback


def _source_refs_from_assets(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for row in rows:
        role = _clean(row["asset_role"]) or "asset"
        remote_url = _clean(row["remote_url"])
        local_path = _clean(row["local_rel_path"])
        gcs_key = _clean(row["gcs_key"])
        if remote_url:
            refs.append({"kind": "external", "role": role, "uri": remote_url})
        elif gcs_key:
            refs.append({"kind": "gcs", "role": role, "uri": f"gs://{gcs_key}"})
        elif local_path:
            refs.append({"kind": "local", "role": role, "uri": local_path})
    return refs


def _canonical_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise CatalogError(f"canonical Patra Darpan SQLite database is missing: {path}")
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        table_names = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        required = {"documents", "asset_refs"}
        missing = required - table_names
        if missing:
            raise CatalogError(f"canonical SQLite is missing tables: {sorted(missing)}")

        source_rows: dict[str, list[sqlite3.Row]] = {}
        if "document_sources" in table_names:
            for row in conn.execute(
                "SELECT * FROM document_sources ORDER BY source_row_id"
            ):
                source_rows.setdefault(str(row["doc_id"]), []).append(row)

        asset_rows: dict[str, list[sqlite3.Row]] = {}
        for row in conn.execute(
            "SELECT * FROM asset_refs ORDER BY asset_id"
        ):
            asset_rows.setdefault(str(row["doc_id"]), []).append(row)

        output: list[dict[str, Any]] = []
        for row in conn.execute("SELECT * FROM documents ORDER BY doc_id"):
            raw_id = str(row["doc_id"])
            doc_id = _document_id(raw_id, "patra-darpan")
            authors = []
            author = _clean(row["author_display"])
            if author:
                authors = [author]
            refs = _source_refs_from_assets(asset_rows.get(raw_id, []))
            provenance = source_rows.get(raw_id, [])
            for source in provenance:
                source_path = _clean(source["source_path"])
                if source_path:
                    # Canonical SQLite currently records local absolute input
                    # paths.  Do not copy those host paths into a portable
                    # release; retain only a stable metadata locator.
                    source_uri = (
                        f"metadata://{Path(source_path).name}"
                        if Path(source_path).is_absolute()
                        else source_path
                    )
                else:
                    source_uri = None
                if source_uri and not any(ref.get("uri") == source_uri for ref in refs):
                    refs.append(
                        {
                            "kind": "metadata",
                            "role": _clean(source["source_type"]) or "metadata",
                            "uri": source_uri,
                            "version": _clean(source["source_version"]),
                        }
                    )
            output.append(
                {
                    "doc_id": doc_id,
                    "source_kind": "patra-darpan",
                    "source_doc_id": raw_id,
                    "title": _clean(row["title"]),
                    "authors": authors,
                    "year": _clean(row["year"]),
                    "journal": _clean(row["journal_label"]),
                    "categories": [],
                    "repo_path": None,
                    "source_refs": refs,
                    "content_sha256": None,
                    "metadata_status": "available",
                    "authority": "patra-darpan.sqlite",
                }
            )
        return output
    except sqlite3.Error as exc:
        raise CatalogError(f"cannot read canonical SQLite {path}: {exc}") from exc
    finally:
        try:
            conn.close()
        except UnboundLocalError:
            pass


def _manifest_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise CatalogError(f"retrieval source manifest is missing: {path}")
    try:
        if path.suffix.lower() == ".jsonl":
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            return [row for row in rows if isinstance(row, dict)]
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"cannot read retrieval source manifest {path}: {exc}") from exc
    if isinstance(value, dict) and isinstance(value.get("sources"), list):
        return [row for row in value["sources"] if isinstance(row, dict)]
    if isinstance(value, dict) and isinstance(value.get("documents"), list):
        return [row for row in value["documents"] if isinstance(row, dict)]
    if isinstance(value, dict):
        return [value]
    raise CatalogError(f"retrieval source manifest is not an object/list: {path}")


def _manifest_catalog_rows(path: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source in _manifest_rows(path):
        kind = _source_kind(source.get("source_kind"))
        raw_id = source.get("document_id") or source.get("source_id") or source.get("source_doc_id")
        doc_id = _document_id(raw_id, kind)
        authors = source.get("authors")
        if authors is None and source.get("author"):
            authors = [source.get("author")]
        repo_path = _clean(source.get("repo_path"))
        if repo_path and (Path(repo_path).is_absolute() or ".." in Path(repo_path).parts):
            repo_path = None
        output.append(
            {
                "doc_id": doc_id,
                "source_kind": kind,
                "source_doc_id": _clean(source.get("source_doc_id")) or str(raw_id or ""),
                "title": _clean(source.get("title")),
                "authors": [str(value) for value in _json_list(authors) if _clean(value)],
                "year": _clean(source.get("year")),
                "journal": _clean(source.get("journal")),
                "categories": [str(value) for value in _json_list(source.get("categories")) if _clean(value)],
                "repo_path": repo_path,
                "source_refs": [value for value in _json_list(source.get("source_refs")) if isinstance(value, dict)],
                "content_sha256": _clean(source.get("content_sha256")),
                "metadata_status": "available" if source.get("title") or source.get("repo_path") else "partial",
                "authority": "sanchaya.manifest" if kind == "sanchaya" else "patra-darpan.manifest",
            }
        )
    return output


def _merge_rows(
    canonical: list[dict[str, Any]], manifest: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    # Keep the complete Patra Darpan metadata authority in the catalog. The
    # release manifest marks which rows have content projections in this
    # release; it must not hide bibliographic records that are not exported
    # yet. Sanchaya rows exist only when they are present in that manifest.
    selected_ids = {str(row["doc_id"]) for row in manifest}
    by_id = {str(row["doc_id"]): dict(row) for row in canonical}
    for row in by_id.values():
        row["indexed_in_release"] = str(row.get("doc_id")) in selected_ids
    for candidate in manifest:
        doc_id = str(candidate["doc_id"])
        current = by_id.get(doc_id)
        if current is None:
            current = dict(candidate)
            by_id[doc_id] = current
        current["indexed_in_release"] = True
        # The canonical SQLite row remains authoritative. The manifest may
        # fill release-specific fields such as repo_path and content hash.
        for key in ("repo_path", "content_sha256", "categories", "source_refs"):
            value = candidate.get(key)
            if value and not current.get(key):
                current[key] = value
    return [by_id[key] for key in sorted(by_id)]


def build_retrieval_catalog(
    canonical_sqlite: Path,
    source_manifest: Path,
    output: Path,
    *,
    release_id: str = "",
    sanchaya_commit: str = "",
    patra_darpan_commit: str = "",
) -> dict[str, Any]:
    """Build one immutable release catalog from both source authorities."""

    rows = _merge_rows(_canonical_rows(canonical_sqlite), _manifest_catalog_rows(source_manifest))
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    conn = sqlite3.connect(output)
    try:
        conn.executescript(CATALOG_SCHEMA)
        conn.executemany(
            """
            INSERT INTO documents (
                doc_id, source_kind, source_doc_id, title, authors_json, year,
                journal, categories_json, repo_path, source_refs_json,
                content_sha256, indexed_in_release, metadata_status, authority
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["doc_id"],
                    row["source_kind"],
                    row.get("source_doc_id"),
                    row.get("title"),
                    json.dumps(row.get("authors") or [], ensure_ascii=False, separators=(",", ":")),
                    row.get("year"),
                    row.get("journal"),
                    json.dumps(row.get("categories") or [], ensure_ascii=False, separators=(",", ":")),
                    row.get("repo_path"),
                    json.dumps(row.get("source_refs") or [], ensure_ascii=False, separators=(",", ":")),
                    row.get("content_sha256"),
                    1 if row.get("indexed_in_release") else 0,
                    row.get("metadata_status") or "partial",
                    row.get("authority") or "unknown",
                )
                for row in rows
            ],
        )
        counts = Counter(str(row["source_kind"]) for row in rows)
        info = {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "catalog_scope": "full-patra-darpan-metadata-plus-release-content",
            "release_id": release_id,
            "source_manifest": str(source_manifest),
            "sanchaya_commit": sanchaya_commit,
            "patra_darpan_commit": patra_darpan_commit,
            "document_count": str(len(rows)),
            "patra_darpan_document_count": str(counts.get("patra-darpan", 0)),
            "sanchaya_document_count": str(counts.get("sanchaya", 0)),
            "indexed_document_count": str(sum(1 for row in rows if row.get("indexed_in_release"))),
            "metadata_only_document_count": str(sum(1 for row in rows if not row.get("indexed_in_release"))),
        }
        conn.executemany(
            "INSERT INTO catalog_info (key, value) VALUES (?, ?)",
            sorted(info.items()),
        )
        conn.commit()
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise CatalogError(f"retrieval catalog integrity check failed: {integrity}")
    except sqlite3.Error as exc:
        raise CatalogError(f"cannot build retrieval catalog {output}: {exc}") from exc
    finally:
        conn.close()
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "document_count": len(rows),
        "patra_darpan_document_count": counts.get("patra-darpan", 0),
        "sanchaya_document_count": counts.get("sanchaya", 0),
        "indexed_document_count": sum(1 for row in rows if row.get("indexed_in_release")),
        "metadata_only_document_count": sum(1 for row in rows if not row.get("indexed_in_release")),
    }


class CatalogAdapter:
    """Read-only metadata queries over a release catalog."""

    def __init__(self, release: Any):
        self.release = release
        self.path: Path | None = None
        self.conn: sqlite3.Connection | None = None
        self.catalog_schema_version = 0
        self.legacy_rows: dict[str, dict[str, Any]] = {}
        artifacts = release.record.get("artifacts") or {}
        if isinstance(artifacts.get("retrieval_catalog"), dict):
            self.path = release.artifact_path("retrieval_catalog")
            try:
                expected_hash = release.artifact_hash("retrieval_catalog")
                if expected_hash:
                    actual_hash = _sha256_file(self.path)
                    if actual_hash != expected_hash:
                        raise CatalogError(
                            "retrieval catalog hash does not match release: "
                            f"catalog={actual_hash} release={expected_hash}"
                        )
                uri = f"file:{self.path}?mode=ro&immutable=1"
                self.conn = sqlite3.connect(uri, uri=True)
                self.conn.row_factory = sqlite3.Row
                version = self.conn.execute("PRAGMA user_version").fetchone()[0]
                if int(version) not in {1, 2}:
                    raise CatalogError(f"unsupported retrieval catalog user_version: {version}")
                self.catalog_schema_version = int(version)
                tables = {
                    str(row["name"])
                    for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                missing = {"catalog_info", "documents"} - tables
                if missing:
                    raise CatalogError(f"retrieval catalog is missing tables: {sorted(missing)}")
                info = {
                    str(row["key"]): str(row["value"])
                    for row in self.conn.execute("SELECT key, value FROM catalog_info")
                }
                catalog_commit = info.get("sanchaya_commit")
                if catalog_commit and catalog_commit != release.corpus_revision:
                    raise CatalogError(
                        "retrieval catalog Sanchaya revision does not match active release: "
                        f"catalog={catalog_commit} release={release.corpus_revision}"
                    )
            except sqlite3.Error as exc:
                raise CatalogError(f"cannot open retrieval catalog {self.path}: {exc}") from exc
        else:
            # Compatibility for releases created before retrieval.catalog.v1.
            # New releases must package retrieval_catalog.sqlite.
            try:
                rows = read_jsonl(release.artifact_path("corpus_manifest"))
            except Exception:
                rows = []
            for row in rows:
                row.setdefault("indexed_in_release", True)
                for key in (row.get("document_id"), row.get("source_doc_id")):
                    if key:
                        self.legacy_rows[str(key)] = row

    @property
    def backend(self) -> str:
        return "sqlite" if self.conn is not None else "legacy-jsonl"

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    @staticmethod
    def _public(row: sqlite3.Row | dict[str, Any], *, corpus_revision: str) -> dict[str, Any]:
        def get(name: str, fallback: str | None = None) -> Any:
            if isinstance(row, dict):
                if name in row:
                    return row.get(name)
                return row.get(fallback) if fallback else None
            keys = row.keys()
            if name in keys:
                return row[name]
            return row[fallback] if fallback and fallback in keys else None

        source_kind = get("source_kind") or "unknown"
        authors_raw = get("authors_json", "authors")
        categories_raw = get("categories_json", "categories")
        source_refs_raw = get("source_refs_json", "source_refs")
        indexed_raw = get("indexed_in_release")
        # v1 catalogs were release-scoped, so every row in one of those
        # catalogs necessarily had a content projection.  v2 records the
        # distinction explicitly while retaining this compatibility behavior.
        indexed_in_release = True if indexed_raw is None else bool(int(indexed_raw))
        return {
            "document_id": get("doc_id") or get("document_id"),
            "source_kind": source_kind,
            "source_doc_id": get("source_doc_id"),
            "title": get("title"),
            "authors": _json_list(authors_raw),
            "year": get("year"),
            "journal": get("journal"),
            "categories": _json_list(categories_raw),
            "repo_path": get("repo_path"),
            "source_refs": [value for value in _json_list(source_refs_raw) if isinstance(value, dict)],
            "content_sha256": get("content_sha256"),
            "indexed_in_release": indexed_in_release,
            "metadata_status": get("metadata_status") or "partial",
            "authority": get("authority") or "unknown",
            "corpus_revision": corpus_revision,
        }

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        document_id = str(document_id or "").strip()
        if not document_id:
            return None
        if self.conn is None:
            row = self.legacy_rows.get(document_id)
            return self._public(row, corpus_revision=self.release.corpus_revision) if row else None
        row = self.conn.execute(
            "SELECT * FROM documents WHERE doc_id = ?",
            (document_id,),
        ).fetchone()
        return self._public(row, corpus_revision=self.release.corpus_revision) if row else None

    def get_documents(self, document_ids: Iterable[str]) -> list[dict[str, Any]]:
        wanted = [str(value).strip() for value in document_ids if str(value).strip()]
        if not wanted:
            return []
        if self.conn is None:
            return [
                self._public(self.legacy_rows[value], corpus_revision=self.release.corpus_revision)
                for value in wanted
                if value in self.legacy_rows
            ]
        placeholders = ",".join("?" for _ in wanted)
        rows = self.conn.execute(
            f"SELECT * FROM documents WHERE doc_id IN ({placeholders})",
            wanted,
        ).fetchall()
        by_id = {str(row["doc_id"]): row for row in rows}
        return [
            self._public(by_id[value], corpus_revision=self.release.corpus_revision)
            for value in wanted
            if value in by_id
        ]

    def search_documents(
        self,
        query: str = "",
        *,
        source_kind: str | None = None,
        year: str | None = None,
        category: str | None = None,
        indexed_in_release: bool | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 50))
        query = str(query or "").strip()
        if source_kind:
            normalized_source_kind = _source_kind(source_kind, fallback="")
            if not normalized_source_kind:
                raise CatalogError("source_kind must be patra-darpan or sanchaya")
            source_kind = normalized_source_kind
        year = str(year).strip() if year else None
        category = str(category).strip() if category else None
        if self.conn is None:
            rows = list(self.legacy_rows.values())
            result: list[dict[str, Any]] = []
            for row in rows:
                public = self._public(row, corpus_revision=self.release.corpus_revision)
                haystack = " ".join(
                    [str(public.get("title") or ""), *[str(v) for v in public.get("authors") or []], str(public.get("repo_path") or "")]
                ).casefold()
                if query and query.casefold() not in haystack:
                    continue
                if source_kind and public.get("source_kind") != source_kind:
                    continue
                if year and str(public.get("year") or "") != year:
                    continue
                if category and category.casefold() not in {str(v).casefold() for v in public.get("categories") or []}:
                    continue
                if indexed_in_release is not None and public.get("indexed_in_release") != indexed_in_release:
                    continue
                result.append(public)
                if len(result) >= limit:
                    break
        else:
            clauses: list[str] = []
            params: list[Any] = []
            if query:
                like = f"%{query}%"
                clauses.append("(title LIKE ? COLLATE NOCASE OR authors_json LIKE ? COLLATE NOCASE OR repo_path LIKE ? COLLATE NOCASE OR journal LIKE ? COLLATE NOCASE)")
                params.extend([like, like, like, like])
            if source_kind:
                clauses.append("source_kind = ?")
                params.append(source_kind)
            if year:
                clauses.append("year = ?")
                params.append(year)
            if category:
                clauses.append("categories_json LIKE ? COLLATE NOCASE")
                params.append(f"%{category}%")
            if indexed_in_release is not None:
                clauses.append("indexed_in_release = ?")
                params.append(1 if indexed_in_release else 0)
            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = self.conn.execute(
                f"SELECT * FROM documents{where} ORDER BY title COLLATE NOCASE, doc_id LIMIT ?",
                [*params, limit],
            ).fetchall()
            result = [self._public(row, corpus_revision=self.release.corpus_revision) for row in rows]
        return {
            "schema_version": "retrieval.document-search.v1",
            "query": query,
            "filters": {
                "source_kind": source_kind,
                "year": year,
                "category": category,
                "indexed_in_release": indexed_in_release,
            },
            "results": result,
            "backend": self.backend,
            "corpus_revision": self.release.corpus_revision,
            "catalog_revision": self.release.catalog_revision,
        }

    def author_works(
        self,
        author: str,
        *,
        indexed_in_release: bool | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        author = str(author or "").strip()
        if not author:
            raise CatalogError("author must not be empty")
        limit = max(1, min(int(limit), 100))
        query_key = _author_key(author)
        if not query_key:
            raise CatalogError("author must contain letters or numbers")

        # Author names are stored as a JSON display list because the upstream
        # Patra Darpan schema currently supplies one display string.  Keep the
        # tolerant comparison here rather than changing that source authority
        # or requiring a migration just to handle initials and punctuation.
        if self.conn is None:
            rows = [self._public(row, corpus_revision=self.release.corpus_revision) for row in self.legacy_rows.values()]
        else:
            rows = [
                self._public(row, corpus_revision=self.release.corpus_revision)
                for row in self.conn.execute("SELECT * FROM documents ORDER BY title COLLATE NOCASE, doc_id")
            ]

        result: list[dict[str, Any]] = []
        for row in rows:
            if indexed_in_release is not None and row.get("indexed_in_release") != indexed_in_release:
                continue
            candidates = [str(value) for value in row.get("authors") or []]
            if not any(query_key in _author_key(candidate) for candidate in candidates):
                continue
            result.append(row)
            if len(result) >= limit:
                break
        return {
            "schema_version": "retrieval.author-works.v1",
            "author": author,
            "filters": {"indexed_in_release": indexed_in_release},
            "results": result,
            "backend": self.backend,
            "corpus_revision": self.release.corpus_revision,
            "catalog_revision": self.release.catalog_revision,
        }

    def corpus_info(self) -> dict[str, Any]:
        if self.conn is None:
            counts = Counter(str(row.get("source_kind") or "unknown") for row in self.legacy_rows.values())
            total = len(self.legacy_rows)
        else:
            counts = Counter(
                {str(row["source_kind"]): int(row["count"]) for row in self.conn.execute("SELECT source_kind, COUNT(*) AS count FROM documents GROUP BY source_kind")}
            )
            total = sum(counts.values())
        if self.conn is None or self.catalog_schema_version < 2:
            indexed_count = total
        else:
            indexed_count = int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM documents WHERE indexed_in_release = 1"
                ).fetchone()[0]
            )
        return {
            "schema_version": "retrieval.corpus-info.v1",
            "catalog_backend": self.backend,
            "document_count": total,
            "indexed_document_count": indexed_count,
            "metadata_only_document_count": total - indexed_count,
            "document_counts_by_source": dict(counts),
            "release_metrics": dict(self.release.record.get("metrics") or {}),
            "corpus_revision": self.release.corpus_revision,
            "catalog_revision": self.release.catalog_revision,
            "release_id": self.release.release_id,
        }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
    return rows
