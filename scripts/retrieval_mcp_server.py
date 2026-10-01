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
            "Read-only retrieval over one release. Read retrieval://search-guide or "
            "get_corpus_info for coverage, query syntax and paging. Read ontology context for entities; "
            "use get_author_works or search_documents for metadata questions; "
            "lookup_entity also returns bounded ontology attributes and labelled incoming/outgoing relations. "
            "Treat these as curated/pilot assertions, not passage evidence; follow related entities by preferred label "
            "and check truncation flags. Resolve entities before passing canonical IDs to search; use stable "
            "chunk/document references and fetch_passages for multiple evidence "
            "items; cite fetched evidence using readable Markdown hyperlinks to citation_url "
            "or source_url, naming the work/paper and location rather than presenting opaque IDs. "
            "Raw Zoekt syntax is supported in lexical mode, including file:Jyo type:filename सूर्य "
            "for filenames of matching files. Generated Sanskrit forms are search hypotheses."
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
        description="Compact ontology vocabulary and normalization; use lookup_entity for bounded attributes, labelled relations and curation references.",
        mime_type="application/json",
    )
    def ontology_context() -> str:
        return json.dumps(service.entities.ontology_context, ensure_ascii=False)

    @server.resource(
        "retrieval://search-guide", name="search_guide",
        description="Index scope, Zoekt syntax, filename-only results, paging, script expansion, Sanskrit exploration and hyperlinks.",
        mime_type="text/markdown",
    )
    def search_guide() -> str:
        return (Path(__file__).resolve().parents[1] / "docs/retrieval/search-guide.md").read_text(encoding="utf-8")

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
        description=("Resolve a name/alias to canonical IDs and corpus occurrence counts; return bounded "
                     "ontology attributes, labelled incoming/outgoing relations, ontology version and curation references. "
                     "These are ontology assertions, not passage evidence. Follow related entities using "
                     "target_preferred_label; check knowledge/results truncation flags."),
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
        description="Report release/index coverage and search capabilities; read retrieval://search-guide for syntax and best practices.",
    )
    def get_corpus_info() -> dict[str, Any]:
        try:
            return service.get_corpus_info()
        except RetrievalError as exc:
            return _error(exc)

    @server.tool(
        name="search_corpus",
        description=("Search lexical Zoekt, semantic vectors, or ranked hybrid results. Read retrieval://search-guide. "
                     "Lexical query accepts raw Zoekt syntax (AND, OR, regex, file:, exclusions, type:filename). "
                     "result_type='files' returns filenames of matching files without content; it uses lexical mode. "
                     "Optional script_expansion accepts plain Sanskrit terms in devanagari/iast/harvard_kyoto/auto; "
                     "use file_filter for path scope. Follow next_cursor with identical lexical query/options; "
                     "backend_counts are returned rows, not total occurrences. Cite citation_url/source_url."),
    )
    def search_corpus(
        query: str,
        mode: str = "hybrid",
        limit: int = 10,
        entity_ids: list[str] | None = None,
        result_type: str = "matches",
        file_filter: str | None = None,
        script_expansion: str = "none",
        context_lines: int = 0,
        snippet_chars: int = 400,
        match_limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        try:
            return service.search(query, mode=mode, limit=limit, entity_ids=entity_ids or [],
                                  result_type=result_type, file_filter=file_filter,
                                  script_expansion=script_expansion, context_lines=context_lines,
                                  snippet_chars=snippet_chars, match_limit=match_limit, cursor=cursor)
        except RetrievalError as exc:
            return _error(exc)

    @server.tool(
        name="fetch_passage",
        description=("Fetch release passages by chunk, document or repo_path. Page documents with offset/next_offset; "
                     "for shortened text, fetch its chunk_id with text_offset=next_text_offset. "
                     "Only release-chunked documents are fetchable. Cite citation_url/source_url."),
    )
    def fetch_passage(
        chunk_id: str | None = None,
        document_id: str | None = None,
        repo_path: str | None = None,
        limit: int = 5,
        offset: int = 0,
        text_offset: int = 0,
        max_chars: int = 4000,
    ) -> dict[str, Any]:
        try:
            return service.passages.fetch(
                chunk_id=chunk_id or None,
                document_id=document_id or None,
                repo_path=repo_path or None,
                limit=limit, offset=offset, text_offset=text_offset, max_chars=max_chars,
            )
        except RetrievalError as exc:
            return _error(exc)

    @server.tool(
        name="fetch_passages",
        description="Fetch several bounded passages in one call using search result references.",
    )
    def fetch_passages(requests: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            return service.fetch_passages(requests)
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
