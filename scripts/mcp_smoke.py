#!/usr/bin/env python3
"""Run a protocol-level MCP smoke check against the retrieval service."""

from __future__ import annotations

import argparse
import asyncio
import json
import os


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("MCP_URL", "http://127.0.0.1:8787/mcp"))
    parser.add_argument("--entity", default="Śraviṣṭhā")
    parser.add_argument("--query", default="Maghādi")
    parser.add_argument("--search-features", action="store_true", help="Verify bounded search, filename-only results, expansion, resources and passage paging")
    parser.add_argument("--catalog-sql", action="store_true", help="Require the optional catalogue SQL tool/resource and reconcile SQL coverage with corpus info")
    parser.add_argument("--figure-chunk-id", help="Verify a specific figure-bearing passage and its MCP image block")
    return parser.parse_args()


def structured(result: object) -> dict:
    data = getattr(result, "structuredContent", None)
    return data if isinstance(data, dict) else {}


async def run(args: argparse.Namespace) -> int:
    try:
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ModuleNotFoundError as exc:  # pragma: no cover - image dependency guard
        raise SystemExit(f"MCP smoke dependencies are missing: {exc}") from exc

    token = os.getenv("MCP_BEARER_TOKEN")
    if not token:
        raise SystemExit("MCP_BEARER_TOKEN is not set")

    timeout = httpx.Timeout(120.0, connect=10.0)
    headers = {"Authorization": f"Bearer {token}"}
    features = {}
    catalog_sql = {}
    figure_smoke = {}
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        async with streamable_http_client(args.url, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                tools = await session.list_tools()
                resources = await session.list_resources()
                if getattr(args, "catalog_sql", False):
                    tool_names = {tool.name for tool in tools.tools}
                    assert "query_catalog" in tool_names, "Catalogue SQL is not enabled"
                    schema_result = await session.read_resource("retrieval://catalog-schema")
                    schema = json.loads(next(item.text for item in schema_result.contents if getattr(item, "text", None)))
                    result = await session.call_tool("query_catalog", {"query":
                        "SELECT SUM(document_count) AS catalogued, "
                        "SUM(CASE WHEN indexed_in_release=1 THEN document_count ELSE 0 END) AS indexed "
                        "FROM coverage_v"})
                    data = structured(result)
                    assert not result.isError and not data["truncated"], data
                    assert len(result.model_dump_json().encode()) < 64000
                    info = structured(await session.call_tool("get_corpus_info", {}))
                    assert data["rows"] == [[info["document_count"], info["indexed_document_count"]]], data
                    assert data["catalog_revision"] == info["catalog_revision"] == schema["catalog_revision"]
                    catalog_sql = {"status": "passed", "catalog_revision": data["catalog_revision"],
                                   "analytics_revision": data["analytics_revision"], "coverage": data["rows"][0]}
                lookup = await session.call_tool(
                    "lookup_entity", {"name": args.entity, "limit": 1}
                )
                lookup_data = structured(lookup)
                assert not lookup.isError and lookup_data.get("results"), lookup_data
                assert len(json.dumps(lookup_data, ensure_ascii=False).encode()) <= 64000
                for row in lookup_data["results"]:
                    assert isinstance(row.get("attributes"), dict) and isinstance(row.get("relations"), list)
                    assert row.get("ontology", {}).get("version")
                    assert "source_ref" in row and "curation_status" in row
                    assert len(row["relations"]) <= 20
                    for relation in row["relations"]:
                        assert relation["direction"] in {"incoming", "outgoing"}
                        assert relation["target_entity_id"] and relation["target_preferred_label"]
                context_resource = await session.read_resource("retrieval://ontology-context")
                context = json.loads(next(item.text for item in context_resource.contents if getattr(item, "text", None)))
                assert context["knowledge_lookup"]["tool"] == "lookup_entity"
                assert {"attributes", "relations"} <= set(context["knowledge_lookup"]["fields"])
                assert context["version"] == lookup_data["results"][0]["ontology"]["version"]
                lookup_tool = next(t for t in tools.tools if t.name == "lookup_entity")
                assert set(lookup_tool.inputSchema["properties"]) == {"name", "type_hint", "limit"}
                assert lookup_tool.inputSchema["required"] == ["name"]
                assert lookup_tool.outputSchema.get("additionalProperties") is not False
                search = await session.call_tool(
                    "search_corpus",
                    {"query": args.query, "mode": "hybrid", "limit": 3},
                )
                if args.figure_chunk_id:
                    figure_result = await session.call_tool("fetch_passage", {
                        "chunk_id": args.figure_chunk_id, "include_figures": True,
                    })
                    figure_data = structured(figure_result)
                    assert not figure_result.isError and figure_data.get("passages"), figure_data
                    figures = figure_data["passages"][0].get("figures", [])
                    assert figures, figure_data
                    assert figures[0]["fig_no"] == 15, figures[0]
                    assert figures[0]["repo_path"].endswith("/media/p20_page.webp"), figures[0]
                    image_blocks = [item for item in figure_result.content if getattr(item, "type", None) == "image"]
                    assert len(image_blocks) == 1, figure_result.content
                    assert image_blocks[0].mimeType == "image/webp", image_blocks[0]
                    async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as image_client:
                        async with image_client.stream("GET", figures[0]["url"]) as image_response:
                            status_code = image_response.status_code
                            content_type = image_response.headers.get("content-type", "")
                    assert status_code == 200, status_code
                    assert content_type.split(";", 1)[0].lower() == "image/webp", content_type
                    figure_smoke = {
                        "status": "passed",
                        "chunk_id": args.figure_chunk_id,
                        "figure_no": figures[0]["fig_no"],
                        "repo_path": figures[0]["repo_path"],
                        "url": figures[0]["url"],
                        "http_status": status_code,
                        "content_type": content_type,
                        "image_blocks": len(image_blocks),
                    }
                if args.search_features:
                    guide = await session.read_resource("retrieval://search-guide")
                    guide_text = "\n".join(getattr(item, "text", "") for item in guide.contents)
                    assert "type:filename" in guide_text and "citation_url" in guide_text
                    search_tool = next(t for t in tools.tools if t.name == "search_corpus")
                    assert "script_expansion" in search_tool.inputSchema["properties"]
                    filename = structured(await session.call_tool("search_corpus", {
                        "query": "file:Jyo type:filename सूर्य", "limit": 3}))
                    assert filename.get("mode") == "lexical" and filename.get("results"), filename
                    assert not filename.get("backend_errors"), filename
                    assert all(m["filename_match"] for r in filename["results"] for m in r["matches"])
                    assert all(r.get("source_url") for r in filename["results"])
                    assert filename["backend_counts"]["vector"] == 0
                    expanded = structured(await session.call_tool("search_corpus", {
                        "query": "सूर्य", "mode": "lexical", "script_expansion": "devanagari",
                        "file_filter": "Jyo", "match_limit": 1, "snippet_chars": 120}))
                    assert not expanded.get("backend_errors") and expanded.get("results"), expanded
                    assert "sūrya" in expanded["query_forms"][0]["forms"]
                    assert len(json.dumps(expanded, ensure_ascii=False).encode()) <= 64000
                    assert all(len(m["line"]) <= 120 for r in expanded["results"] for m in r["matches"])
                    if expanded.get("next_cursor"):
                        continued = structured(await session.call_tool("search_corpus", {
                            "query": "सूर्य", "mode": "lexical", "script_expansion": "devanagari",
                            "file_filter": "Jyo", "match_limit": 1, "snippet_chars": 120,
                            "cursor": expanded["next_cursor"]}))
                        assert not continued.get("backend_errors") and continued.get("results"), continued
                        assert continued["results"] != expanded["results"]
                    chunk_id = next((r.get("chunk_id") for r in structured(search).get("results", []) if r.get("chunk_id")), None)
                    assert chunk_id, "hybrid smoke search must yield a fetchable chunk"
                    fetched = structured(await session.call_tool("fetch_passage", {"chunk_id": chunk_id, "max_chars": 120}))
                    assert fetched.get("passages"), fetched
                    passage = fetched["passages"][0]
                    assert passage.get("citation_url"), passage
                    doc = structured(await session.call_tool("fetch_passage", {"document_id": passage["document_id"], "limit": 1}))
                    assert doc.get("total_passages", 0) > 0
                    if doc["has_more"]:
                        later = structured(await session.call_tool("fetch_passage", {
                            "document_id": passage["document_id"], "offset": doc["next_offset"], "limit": 1}))
                        assert later["passages"][0]["chunk_id"] != doc["passages"][0]["chunk_id"]
                    features = {"guide": "passed", "filename_only": "passed", "script_expansion": "passed",
                                "match_continuation": "passed" if expanded.get("next_cursor") else "not needed for this query",
                                "passage_paging": "passed", "source_links": "passed"}

    lookup_data = structured(lookup)
    search_data = structured(search)
    backend_errors = search_data.get("errors") or search_data.get("backend_errors") or {}
    report = {
        "protocol": getattr(init, "protocolVersion", None),
        "tools": [item.name for item in tools.tools],
        "resources": [str(item.uri) for item in resources.resources],
        "lookup": {
            "error": bool(getattr(lookup, "isError", False)),
            "result_count": len(lookup_data.get("results", [])),
        },
        "search": {
            "error": bool(getattr(search, "isError", False)),
            "result_count": len(search_data.get("results", [])),
            "backend_counts": search_data.get("backend_counts", {}),
            "errors": backend_errors,
        },
        "search_features": features,
        "catalog_sql": catalog_sql,
        "figures": figure_smoke,
        "entity_knowledge": {"lookup": "passed", "context": "passed", "input_schema": "unchanged"},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if getattr(lookup, "isError", False) or not lookup_data.get("results"):
        return 1
    if getattr(search, "isError", False) or backend_errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
