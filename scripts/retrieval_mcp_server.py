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
import hmac
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


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class BearerAuthMiddleware:
    """Protect an ASGI HTTP app with one shared bearer token.

    Authentication is deliberately transport-level and read-only.  The token
    is supplied through the environment, never through the release artifacts,
    and is compared without logging or exposing it in an error response.
    """

    def __init__(self, app: Any, token: str):
        self.app = app
        self.token = token

    @staticmethod
    def _authorization(scope: dict[str, Any]) -> str:
        for name, value in scope.get("headers", []):
            if name.lower() == b"authorization":
                return value.decode("latin-1")
        return ""

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        authorization = self._authorization(scope)
        scheme, separator, credentials = authorization.partition(" ")
        valid = (
            separator == " "
            and scheme.casefold() == "bearer"
            and hmac.compare_digest(credentials.strip(), self.token)
        )
        if valid:
            await self.app(scope, receive, send)
            return

        body = b'{"error":"unauthorized"}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"www-authenticate", b'Bearer realm="retrieval-mcp"'),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def build_mcp(service: RetrievalService, *, oauth_provider: Any | None = None):
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "MCP server needs the v1 Python SDK: run with `uv run --with 'mcp<2>' ...`"
        ) from exc

    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8787"))
    auth_settings = oauth_provider.auth_settings() if oauth_provider is not None else None
    server = FastMCP(
        "Sanchaya Retrieval",
        instructions=(
            "Read-only retrieval over one release. Read ontology context first; "
            "use get_author_works or search_documents for metadata questions; "
            "resolve entities before passing canonical IDs to search; use stable "
            "chunk/document references and fetch_passages for multiple evidence "
            "items; cite fetched passages."
        ),
        host=host,
        port=port,
        stateless_http=True,
        json_response=True,
        auth_server_provider=oauth_provider,
        auth=auth_settings,
    )

    if oauth_provider is not None:

        @server.custom_route("/oauth/callback", methods=["GET"], include_in_schema=False)
        async def oauth_callback(request):
            return await oauth_provider.handle_callback(request)

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
        name="get_document_metadata",
        description="Return bounded catalog metadata and provenance for one stable document ID.",
    )
    def get_document_metadata(document_id: str) -> dict[str, Any]:
        try:
            return service.get_document_metadata(document_id)
        except RetrievalError as exc:
            return _error(exc)

    @server.tool(
        name="get_documents_metadata",
        description="Batch-resolve bounded catalog metadata for stable document IDs.",
    )
    def get_documents_metadata(document_ids: list[str]) -> dict[str, Any]:
        try:
            return service.get_documents_metadata(document_ids[:50])
        except RetrievalError as exc:
            return _error(exc)

    @server.tool(
        name="search_documents",
        description="Search the complete document metadata catalog without full-text retrieval. Results include indexed_in_release; set it true to restrict to documents with content in this release.",
    )
    def search_documents(
        query: str = "",
        source_kind: str | None = None,
        year: str | None = None,
        category: str | None = None,
        indexed_in_release: bool | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        try:
            return service.search_documents(
                query,
                source_kind=source_kind,
                year=year,
                category=category,
                indexed_in_release=indexed_in_release,
                limit=limit,
            )
        except RetrievalError as exc:
            return _error(exc)

    @server.tool(
        name="get_author_works",
        description="Find all cataloged works for an author without repeated full-text searches. Results include indexed_in_release; set it true to restrict to documents with content in this release.",
    )
    def get_author_works(
        author: str,
        indexed_in_release: bool | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        try:
            return service.get_author_works(
                author,
                indexed_in_release=indexed_in_release,
                limit=limit,
            )
        except RetrievalError as exc:
            return _error(exc)

    @server.tool(
        name="get_corpus_info",
        description="Return corpus source counts, catalog backend, release identity, and entity-index coverage.",
    )
    def get_corpus_info() -> dict[str, Any]:
        try:
            return service.get_corpus_info()
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
        name="fetch_passages",
        description="Fetch several bounded passages in one call using search result references.",
    )
    def fetch_passages(requests: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            return service.fetch_passages(requests[:50])
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
        auth_mode = os.getenv("MCP_AUTH_MODE", "bearer").strip().lower()
        if auth_mode not in {"bearer", "oauth"}:
            raise ValueError("MCP_AUTH_MODE must be bearer or oauth")
        oauth_provider = None
        if auth_mode == "oauth":
            from lib.retrieval_oauth import GoogleOAuthProvider

            oauth_provider = GoogleOAuthProvider.from_env()
        server = build_mcp(service, oauth_provider=oauth_provider)
    except (RetrievalError, OSError, ValueError) as exc:
        print(f"retrieval MCP configuration error: {exc}", file=sys.stderr)
        return 2
    transport = os.getenv("MCP_TRANSPORT", "streamable-http").strip().lower()
    if transport not in {"stdio", "sse", "streamable-http"}:
        print(f"unsupported MCP_TRANSPORT: {transport}", file=sys.stderr)
        return 2
    if transport == "streamable-http":
        app = server.streamable_http_app()
        if auth_mode == "bearer":
            token = os.getenv("MCP_BEARER_TOKEN", "").strip()
            auth_required = _env_bool("MCP_AUTH_REQUIRED", default=True)
            if auth_required and not token:
                print(
                    "MCP_BEARER_TOKEN is required for streamable HTTP; "
                    "set MCP_AUTH_REQUIRED=false only for an explicitly local test",
                    file=sys.stderr,
                )
                return 2
            if token:
                app = BearerAuthMiddleware(app, token)
        try:
            import uvicorn
        except ModuleNotFoundError as exc:
            print("streamable HTTP needs uvicorn", file=sys.stderr)
            return 2
        uvicorn.run(
            app,
            host=os.getenv("MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("MCP_PORT", "8787")),
            log_level=os.getenv("MCP_LOG_LEVEL", "info"),
        )
    else:
        # stdio and SSE are retained for local tooling.  The bearer-token
        # boundary applies to the HTTP service exposed to MCP clients.
        server.run(transport=transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
