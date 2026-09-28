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
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        async with streamable_http_client(args.url, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                tools = await session.list_tools()
                resources = await session.list_resources()
                lookup = await session.call_tool(
                    "lookup_entity", {"name": args.entity, "limit": 1}
                )
                search = await session.call_tool(
                    "search_corpus",
                    {"query": args.query, "mode": "hybrid", "limit": 3},
                )

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
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if getattr(lookup, "isError", False) or not lookup_data.get("results"):
        return 1
    if getattr(search, "isError", False) or backend_errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
