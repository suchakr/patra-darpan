from __future__ import annotations

import base64
import copy
import importlib.util
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lib.retrieval_adapters import PassageStore
from lib.retrieval_figures import (
    MAX_FIGURE_BYTES,
    fetch_figure,
    figures_for_chunk,
    figures_from_document,
    raw_url,
)


REVISION = "c07b047803818f09647b0f44d616d43a4969c353"
DOC_PATH = "patra-darpan/papers/Space Paper/document.md"
MARKDOWN = """# Paper

The text introduces Fig. 1.

![Fig. 1. A diagram](media/fig 1.webp)

*Fig. 1. A diagram.*
<!-- figure-resolved-page: page=7 image=media/fig 1.webp -->
<!-- figure-meta: page=7, position=top, type=diagram -->

![Figure 2. चित्र](media/चित्र.webp)
<!-- figure-meta: page=8, position=middle, type=photograph -->

![External](https://example.org/image.webp)
![Escapes](../../private.webp)
"""


class FigureReferenceTests(unittest.TestCase):
    def test_relative_paths_metadata_and_revision_pinned_encoded_urls(self):
        figures = figures_from_document(DOC_PATH, MARKDOWN, REVISION)
        self.assertEqual(len(figures), 2)
        self.assertEqual(figures[0]["caption"], "Fig. 1. A diagram")
        self.assertEqual(figures[0]["repo_path"], "patra-darpan/papers/Space Paper/media/fig 1.webp")
        self.assertEqual(figures[0]["url"], raw_url(REVISION, figures[0]["repo_path"]))
        self.assertIn(f"/{REVISION}/", figures[0]["url"])
        self.assertIn("Space%20Paper/media/fig%201.webp", figures[0]["url"])
        self.assertEqual((figures[0]["page"], figures[0]["type"], figures[0]["fig_no"]),
                         (7, "diagram", 1))
        self.assertEqual(figures[1]["repo_path"], "patra-darpan/papers/Space Paper/media/चित्र.webp")
        self.assertIn("%E0%A4%9A%E0%A4%BF%E0%A4%A4%E0%A5%8D%E0%A4%B0.webp", figures[1]["url"])
        self.assertEqual((figures[1]["page"], figures[1]["type"], figures[1]["fig_no"]),
                         (8, "photograph", 2))

    def test_figure_attachment_uses_source_block_or_matching_number_and_deduplicates(self):
        figures = figures_from_document(DOC_PATH, MARKDOWN, REVISION)
        first_block = figures[0]["_source_block"]
        selected = figures_for_chunk(figures, f"block:{first_block}-{first_block}:chunk:3", "mentions Figure 2")
        self.assertEqual([figure["fig_no"] for figure in selected], [1, 2])
        self.assertEqual(set(selected[0]), {"caption", "repo_path", "url", "page", "type", "fig_no"})
        only_second = figures_for_chunk(figures, "block:1-1:chunk:1", "Fig. 2 is shown here")
        self.assertEqual([figure["fig_no"] for figure in only_second], [2])

    def test_external_refs_and_paths_escaping_papers_are_rejected(self):
        figures = figures_from_document(DOC_PATH, MARKDOWN, REVISION)
        paths = {figure["repo_path"] for figure in figures}
        self.assertNotIn("https://example.org/image.webp", paths)
        self.assertFalse(any("private.webp" in path for path in paths))
        escaped = figures_from_document(
            DOC_PATH, "![escape](%252e%252e/%252e%252e/private.webp)", REVISION,
        )
        self.assertEqual(escaped, [])
        outside_source = figures_from_document("Jyotisham/document.md", MARKDOWN, REVISION)
        self.assertEqual(outside_source, [])

    def test_parent_relative_path_is_normalized_when_still_inside_papers(self):
        figures = figures_from_document(
            DOC_PATH,
            "![Fig. 3. Shared](../Shared Figures/fig 3.webp)\n"
            "<!-- figure-meta: page=9, position=top, type=diagram -->",
            REVISION,
        )
        self.assertEqual(len(figures), 1)
        self.assertEqual(
            figures[0]["repo_path"],
            "patra-darpan/papers/Shared Figures/fig 3.webp",
        )

    def test_empty_document_has_no_figures(self):
        self.assertEqual(figures_from_document(DOC_PATH, "No figure here.", REVISION), [])

    def test_passage_and_batch_results_always_include_figures_and_cache_document(self):
        store = PassageStore.__new__(PassageStore)
        store.release = SimpleNamespace(
            corpus_revision=REVISION, catalog_revision="catalog",
            record={"source": {"sanchaya_repo": "https://github.com/cahcblr/sanchaya.git"}},
        )
        store.catalog = SimpleNamespace(get_document=lambda _document_id: {})
        row = {
            "chunk_id": "chunk-1", "document_id": "doc-1", "repo_path": DOC_PATH,
            "logical_location": "block:1-1:chunk:1", "text": "Fig. 2 is discussed.",
        }
        row2 = dict(row, chunk_id="chunk-2", logical_location="block:1-1:chunk:2")
        store.chunks = [row, row2]
        store.by_id = {row["chunk_id"]: row, row2["chunk_id"]: row2}
        store.by_repo_path = {DOC_PATH: [row, row2]}
        store.by_document = {"doc-1": [row, row2]}

        with patch("lib.retrieval_adapters.fetch_document_markdown", return_value=MARKDOWN) as fetch_source:
            first = store.fetch(chunk_id="chunk-1")["passages"][0]
            batch = store.fetch_many([{"chunk_id": "chunk-2"}])
        self.assertEqual(first["media"], [])
        self.assertEqual([figure["fig_no"] for figure in first["figures"]], [2])
        self.assertEqual([figure["fig_no"] for figure in batch["results"][0]["passages"][0]["figures"]], [2])
        fetch_source.assert_called_once_with(DOC_PATH, REVISION)


class FakeHeaders:
    def __init__(self, content_type: str, content_length: str | None = None):
        self.content_type = content_type
        self.content_length = content_length

    def get_content_type(self):
        return self.content_type

    def get(self, name: str):
        return self.content_length if name.lower() == "content-length" else None


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "image/webp", content_length: str | None = None):
        self.body = body
        self.offset = 0
        self.headers = FakeHeaders(content_type, content_length)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int) -> bytes:
        part = self.body[self.offset:self.offset + size]
        self.offset += len(part)
        return part


class FigureFetchTests(unittest.TestCase):
    def figure(self):
        path = "patra-darpan/papers/Paper/media/fig.webp"
        return {"repo_path": path, "url": raw_url(REVISION, path)}

    def use_response(self, response):
        opener = Mock()
        opener.open.return_value = response
        return patch("lib.retrieval_figures.urllib.request.build_opener", return_value=opener), opener

    def test_fetch_image_success_and_mime(self):
        patcher, _opener = self.use_response(FakeResponse(b"webp", "image/webp"))
        with patcher:
            self.assertEqual(fetch_figure(self.figure(), REVISION), (b"webp", "image/webp"))

    def test_oversize_timeout_and_non_image_fail_per_figure(self):
        patcher, _ = self.use_response(FakeResponse(b"", "image/webp", str(MAX_FIGURE_BYTES + 1)))
        with patcher, self.assertRaisesRegex(ValueError, "exceeds"):
            fetch_figure(self.figure(), REVISION)

        opener = Mock()
        opener.open.side_effect = TimeoutError("timed out")
        with patch("lib.retrieval_figures.urllib.request.build_opener", return_value=opener):
            with self.assertRaisesRegex(TimeoutError, "timed out"):
                fetch_figure(self.figure(), REVISION)

        patcher, _ = self.use_response(FakeResponse(b"not an image", "text/plain"))
        with patcher, self.assertRaisesRegex(ValueError, "not an image"):
            fetch_figure(self.figure(), REVISION)

    def test_figure_url_cannot_be_substituted(self):
        figure = self.figure()
        figure["url"] = "https://attacker.invalid/image.webp"
        with self.assertRaisesRegex(ValueError, "does not match"):
            fetch_figure(figure, REVISION)


@unittest.skipUnless(importlib.util.find_spec("mcp"), "MCP SDK required for protocol tests")
class FigureMCPTests(unittest.IsolatedAsyncioTestCase):
    def make_service(self):
        path_base = "patra-darpan/papers/Paper/media/fig"
        figures = [
            {"caption": f"Fig. {number}", "repo_path": f"{path_base}{number}.webp",
             "url": raw_url(REVISION, f"{path_base}{number}.webp"), "page": number,
             "type": "diagram", "fig_no": number}
            for number in range(1, 5)
        ]
        payload = {"schema_version": "retrieval.passage.v1", "passages": [{"figures": figures}]}
        return SimpleNamespace(
            release=SimpleNamespace(corpus_revision=REVISION),
            passages=SimpleNamespace(fetch=Mock(return_value=copy.deepcopy(payload))),
        )

    async def test_schema_default_false_and_include_figures_mixed_result_cap_and_errors(self):
        from mcp.shared.memory import create_connected_server_and_client_session
        from scripts.retrieval_mcp_server import build_mcp

        service = self.make_service()
        with patch.dict("os.environ", {"MCP_CATALOG_SQL_ENABLED": "false"}):
            server = build_mcp(service)
            async with create_connected_server_and_client_session(server) as client:
                tools = await client.list_tools()
                tool = next(item for item in tools.tools if item.name == "fetch_passage")
                self.assertIn("include_figures", tool.inputSchema["properties"])
                self.assertFalse(tool.inputSchema["properties"]["include_figures"].get("default", True))

                with patch("scripts.retrieval_mcp_server.fetch_figure") as fetch:
                    text_only = await client.call_tool("fetch_passage", {"chunk_id": "c1"})
                    self.assertFalse(text_only.isError)
                    self.assertFalse(any(getattr(item, "type", None) == "image" for item in text_only.content))
                    self.assertEqual(text_only.structuredContent, service.passages.fetch.return_value)
                    fetch.assert_not_called()

                with patch("scripts.retrieval_mcp_server.fetch_figure", side_effect=[
                    TimeoutError("timed out"), ValueError("too large"), RuntimeError("not image"),
                ]) as fetch:
                    mixed = await client.call_tool("fetch_passage", {
                        "chunk_id": "c1", "include_figures": True,
                    })
                self.assertFalse(mixed.isError, mixed)
                self.assertEqual(fetch.call_count, 3)
                body = mixed.structuredContent
                self.assertTrue(body["figures_truncated"])
                self.assertIn("timed out", body["passages"][0]["figures"][0]["error"])
                self.assertIn("too large", body["passages"][0]["figures"][1]["error"])
                self.assertIn("not image", body["passages"][0]["figures"][2]["error"])
                self.assertFalse(any(getattr(item, "type", None) == "image" for item in mixed.content))
                self.assertEqual(mixed.content[0].text, json.dumps(body, ensure_ascii=False))

    async def test_success_returns_mcp_image_blocks_after_structured_json(self):
        from mcp.shared.memory import create_connected_server_and_client_session
        from scripts.retrieval_mcp_server import build_mcp

        service = self.make_service()
        with patch.dict("os.environ", {"MCP_CATALOG_SQL_ENABLED": "false"}):
            server = build_mcp(service)
            async with create_connected_server_and_client_session(server) as client:
                with patch("scripts.retrieval_mcp_server.fetch_figure", return_value=(b"image", "image/webp")):
                    result = await client.call_tool("fetch_passage", {
                        "chunk_id": "c1", "include_figures": True,
                    })
        self.assertFalse(result.isError, result)
        self.assertEqual(result.content[0].type, "text")
        self.assertEqual(json.loads(result.content[0].text), result.structuredContent)
        images = [item for item in result.content if getattr(item, "type", None) == "image"]
        self.assertEqual(len(images), 3)
        self.assertEqual(images[0].mimeType, "image/webp")
        self.assertEqual(base64.b64decode(images[0].data), b"image")
        self.assertTrue(result.structuredContent["figures_truncated"])
