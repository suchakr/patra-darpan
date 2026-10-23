#!/usr/bin/env python3
"""Read-only F06 candidate smoke via an in-process MCP session and live Zoekt.

Uses the existing release; performs no embeddings, writes or service restarts.
It does not verify HTTP authentication or an interactive OAuth login.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.retrieval_adapters import RetrievalService, json_bytes, load_release
from scripts.retrieval_mcp_server import build_mcp

REGEX = "(धनिष्ठ|धनिष्ट|धनीष्ठ|dhaniṣṭ|dhanishta) -file:patra-darpan/papers"
LITERALS = "(धनिष्ठ or धनिष्ट or धनीष्ठ or dhaniṣṭ or dhanishta) -file:patra-darpan/papers"


async def main() -> None:
    from mcp.shared.memory import create_connected_server_and_client_session

    release = load_release()
    service = RetrievalService(release, ontology_path=os.getenv(
        "RETRIEVAL_ONTOLOGY_PATH", str(ROOT / "ontology/jyotisha-v0.3.json")))
    server = build_mcp(service)
    report = {"release_id": release.release_id, "catalog_revision": release.catalog_revision, "checks": []}
    async with create_connected_server_and_client_session(server) as client:
        tool = next(t for t in (await client.list_tools()).tools if t.name == "search_corpus")
        assert "lowercase 'or'" in tool.description
        for label, query in (("original_regex", REGEX), ("lowercase_or_retry", LITERALS)):
            args = {"query": query, "mode": "lexical", "result_type": "files", "limit": 1}
            started = time.monotonic()
            envelope = await client.call_tool("search_corpus", args)
            assert not envelope.isError, envelope
            result = envelope.structuredContent
            assert json_bytes(result) <= 64000
            assert result["lexical_query"].endswith(" -file:patra-darpan/catalog/ -file:ontology/")
            stats = result["lexical_stats"]
            assert result["search_incomplete"] == (not stats["counts_exact"])
            report["checks"].append({"query": label, "elapsed_seconds": round(time.monotonic() - started, 3),
                                     "stats": stats, "error": result["lexical_error"],
                                     "returned_files": len(result["results"])})
            # The deployed API supports partial responses. An unavailable backend
            # is correctly labelled by the adapter but fails this live smoke.
            assert result["lexical_error"] is None, report
            if label == "original_regex" and result["next_cursor"]:
                args["cursor"] = result["next_cursor"]
                continuation = await client.call_tool("search_corpus", args)
                assert not continuation.isError
                assert continuation.structuredContent["lexical_stats"] == stats
                assert continuation.structuredContent["search_incomplete"] == result["search_incomplete"]
                report["checks"][-1]["continuation"] = "passed"
            if label == "lowercase_or_retry":
                assert stats["counts_exact"] and result["results"], report
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
