#!/usr/bin/env python3
"""Expose the read-only retrieval contract through MCP.

Run with the pinned v1 Python SDK, for example::

    uv run --with 'mcp<2' --with qdrant-client --with sentence-transformers \
      python scripts/retrieval_mcp_server.py

The server does not build an index, edit the ontology, or accept arbitrary
filesystem paths.  It reads one active release record and delegates to the
three backend adapters.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.retrieval_adapters import RetrievalError, RetrievalService, load_release


def ontology_path() -> Path:
    configured = os.getenv("RETRIEVAL_ONTOLOGY_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    root = Path(os.getenv("RETRIEVAL_ONTOLOGY_ROOT", ROOT / "ontology"))
    return (root / "jyotisha-v0.3.json").resolve()


def _error(exc: Exception) -> dict[str, Any]:
    return {
        "schema_version": "retrieval.error.v1",
        "error": {"type": exc.__class__.__name__, "message": str(exc)},
    }


def build_mcp(service: RetrievalService):
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "MCP server needs the v1 Python SDK: run with `uv run --with 'mcp<2>' ...`"
        ) from exc

    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8787"))
    server = FastMCP(
        "Sanchaya Retrieval",
        instructions=(
            "Read-only retrieval over one release. Read ontology context first; "
            "resolve entities before passing canonical IDs to search; cite fetched passages."
        ),
        host=host,
        port=port,
        stateless_http=True,
        json_response=True,
    )

    @server.resource(
        "retrieval://ontology-context",
        name="ontology_context",
        description="Compact read-only starter ontology and normalization guide.",
        mime_type="application/json",
    )
    def ontology_context() -> str:
        return json.dumps(service.entities.ontology_context, ensure_ascii=False)

    @server.resource(
        "retrieval://release",
        name="active_release",
        description="Lineage and artifact identifiers for the active read-only release.",
        mime_type="application/json",
    )
    def active_release() -> str:
        return json.dumps(service.release.record, ensure_ascii=False)

    @server.tool(
        name="lookup_entity",
        description="Resolve an entity name or alias to canonical IDs from the starter registry.",
    )
    def lookup_entity(name: str, type_hint: str | None = None, limit: int = 10) -> dict[str, Any]:
        try:
            return service.entities.lookup(name, type_hint=type_hint, limit=limit)
        except RetrievalError as exc:
            return _error(exc)

    @server.tool(
        name="search_corpus",
        description="Search the lexical, vector, or hybrid corpus projection.",
    )
    def search_corpus(
        query: str,
        mode: str = "hybrid",
        limit: int = 10,
        entity_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            return service.search(query, mode=mode, limit=limit, entity_ids=entity_ids or [])
        except RetrievalError as exc:
            return _error(exc)

    @server.tool(
        name="fetch_passage",
        description="Fetch a bounded passage by chunk, document, or indexed repository path.",
    )
    def fetch_passage(
        chunk_id: str | None = None,
        document_id: str | None = None,
        repo_path: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        try:
            return service.passages.fetch(
                chunk_id=chunk_id or None,
                document_id=document_id or None,
                repo_path=repo_path or None,
                limit=limit,
            )
        except RetrievalError as exc:
            return _error(exc)

    @server.tool(
        name="list_entity_mentions",
        description="Browse resolved mentions and evidence links for a canonical entity ID.",
    )
    def list_entity_mentions(entity_id: str, offset: int = 0, limit: int = 20) -> dict[str, Any]:
        try:
            return service.entities.list_mentions(entity_id, offset=offset, limit=limit)
        except RetrievalError as exc:
            return _error(exc)

    return server


def main() -> int:
    try:
        release = load_release()
        service = RetrievalService(
            release,
            ontology_path=ontology_path(),
            zoekt_url=os.getenv("ZOEKT_URL") or os.getenv("RETRIEVAL_ZOEKT_URL"),
            qdrant_url=os.getenv("QDRANT_URL") or os.getenv("RETRIEVAL_QDRANT_URL"),
        )
        server = build_mcp(service)
    except (RetrievalError, OSError, ValueError) as exc:
        print(f"retrieval MCP configuration error: {exc}", file=sys.stderr)
        return 2
    transport = os.getenv("MCP_TRANSPORT", "streamable-http").strip().lower()
    if transport not in {"stdio", "sse", "streamable-http"}:
        print(f"unsupported MCP_TRANSPORT: {transport}", file=sys.stderr)
        return 2
    server.run(transport=transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
