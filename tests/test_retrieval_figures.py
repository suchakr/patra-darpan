from __future__ import annotations

import base64
import copy
import importlib.util
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lib.retrieval_adapters import PassageStore, RetrievalError
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
SHARED_PAGE_MARKDOWN = """# Paper

<!-- figure-resolved-page-render-hidden: image=media/p10_page.webp caption="Fig. 2. Hidden diagram" -->
<!-- figure-meta: page=10, position=top-left, type=diagram -->

![Fig. 3. Shared page](media/p10_page.webp)
<!-- figure-resolved-page-render: page=10 image=media/p10_page.webp -->
<!-- figure-meta: page=10, position=top-right, type=diagram -->
"""
EXTRACTED_MARKDOWN = """# Paper

![Fig. 2. Extracted diagram](media/p05_page.webp)
<!-- figure-resolved-page-render: page=5 image=media/p05_page.webp -->
<!-- figure-meta: page=5, position=top, type=diagram -->
<!-- figure-resolved-extracted: page=5 image=media/p05_fig01.jpg -->
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

    def test_hidden_page_render_and_shared_page_keep_both_captions(self):
        figures = figures_from_document(DOC_PATH, SHARED_PAGE_MARKDOWN, REVISION)
        self.assertEqual([figure["fig_no"] for figure in figures], [2, 3])
        self.assertEqual([figure["page"] for figure in figures], [10, 10])
        self.assertEqual([figure["caption"] for figure in figures], [
            "Fig. 2. Hidden diagram", "Fig. 3. Shared page",
        ])
        self.assertEqual({figure["repo_path"] for figure in figures}, {
            "patra-darpan/papers/Space Paper/media/p10_page.webp",
        })
        selected = figures_for_chunk(figures, "block:1-1:chunk:1", "Fig. 2 and Fig. 3")
        self.assertEqual([figure["fig_no"] for figure in selected], [2, 3])
        self.assertEqual(len({figure["repo_path"] for figure in selected}), 1)

    def test_extracted_crop_supersedes_page_render_for_same_figure(self):
        figures = figures_from_document(DOC_PATH, EXTRACTED_MARKDOWN, REVISION)
        self.assertEqual(len(figures), 1)
        self.assertEqual(figures[0]["fig_no"], 2)
        self.assertEqual(figures[0]["page"], 5)
        self.assertEqual(figures[0]["repo_path"],
                         "patra-darpan/papers/Space Paper/media/p05_fig01.jpg")
        self.assertEqual(figures[0]["type"], "diagram")

    def test_get_figure_metadata_is_release_pinned_and_can_describe_shared_render(self):
        store = PassageStore.__new__(PassageStore)
        store.release = SimpleNamespace(
            corpus_revision=REVISION,
            record={"source": {"sanchaya_repo": "https://github.com/cahcblr/sanchaya.git"}},
        )
        store.catalog = SimpleNamespace(get_document=lambda _document_id: {
            "source_refs": [{"uri": "https://example.org/paper.pdf"}],
        })
        store.by_repo_path = {
            DOC_PATH: [{"document_id": "doc-1"}],
        }
        store._figure_document_cache = {}
        store._figure_document_cache_lock = threading.Lock()
        path = "patra-darpan/papers/Space Paper/media/p10_page.webp"
        with patch("lib.retrieval_adapters.fetch_document_markdown", return_value=SHARED_PAGE_MARKDOWN):
            figure = store.figure_by_path(path)
        self.assertEqual(figure["fig_no"], [2, 3])
        self.assertEqual(figure["page"], 10)
        self.assertEqual(figure["source_url"], raw_url(REVISION, path))
        self.assertEqual(figure["citation_url"], "https://example.org/paper.pdf")
        self.assertEqual(figure["captions"], ["Fig. 2. Hidden diagram", "Fig. 3. Shared page"])

    def test_get_figure_rejects_unreferenced_and_escaped_paths(self):
        store = PassageStore.__new__(PassageStore)
        store.release = SimpleNamespace(corpus_revision=REVISION)
        store.by_repo_path = {DOC_PATH: [{"document_id": "doc-1"}]}
        with self.assertRaisesRegex(RetrievalError, "outside patra-darpan/papers"):
            store.figure_by_path("patra-darpan/papers/../../private.webp")
        store._figure_document_cache = {}
        store._figure_document_cache_lock = threading.Lock()
        with patch("lib.retrieval_adapters.fetch_document_markdown", return_value=MARKDOWN):
            with self.assertRaisesRegex(RetrievalError, "not referenced"):
                store.figure_by_path("patra-darpan/papers/Space Paper/media/missing.webp")

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
            passages=SimpleNamespace(
                fetch=Mock(return_value=copy.deepcopy(payload)),
                figure_by_path=Mock(return_value={
                    "schema_version": "retrieval.figure.v1",
                    "repo_path": f"{path_base}2.webp",
                    "caption": "Fig. 2",
                    "page": 2,
                    "fig_no": 2,
                    "source_url": raw_url(REVISION, f"{path_base}2.webp"),
                    "citation_url": "https://example.org/paper.pdf",
                    "corpus_revision": REVISION,
                }),
            ),
        )

    async def test_passage_is_json_only_and_get_figure_returns_metadata_text_then_image(self):
        from mcp.shared.memory import create_connected_server_and_client_session
        from scripts.retrieval_mcp_server import build_mcp

        service = self.make_service()
        with patch.dict("os.environ", {"MCP_CATALOG_SQL_ENABLED": "false"}):
            server = build_mcp(service)
            async with create_connected_server_and_client_session(server) as client:
                tools = await client.list_tools()
                names = {item.name for item in tools.tools}
                self.assertIn("get_figure", names)
                passage_tool = next(item for item in tools.tools if item.name == "fetch_passage")
                self.assertNotIn("include_figures", passage_tool.inputSchema["properties"])
                figure_tool = next(item for item in tools.tools if item.name == "get_figure")
                self.assertIn("repo_path", figure_tool.inputSchema["properties"])
                self.assertIn("structuredContent", figure_tool.description)
                self.assertIn("JSON", figure_tool.description)

                text_only = await client.call_tool("fetch_passage", {"chunk_id": "c1"})
                self.assertFalse(text_only.isError, text_only.content)
                self.assertFalse(any(getattr(item, "type", None) == "image" for item in text_only.content))
                self.assertEqual(text_only.structuredContent, service.passages.fetch.return_value)

                with patch("scripts.retrieval_mcp_server.fetch_figure", return_value=(b"image", "image/webp")):
                    result = await client.call_tool("get_figure", {
                        "repo_path": service.passages.figure_by_path.return_value["repo_path"],
                    })
        self.assertFalse(result.isError, result)
        self.assertEqual(result.content[0].type, "text")
        metadata = json.loads(result.content[0].text)
        self.assertEqual(metadata, service.passages.figure_by_path.return_value)
        if result.structuredContent:
            self.assertEqual(result.structuredContent, metadata)
        images = [item for item in result.content if getattr(item, "type", None) == "image"]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].mimeType, "image/webp")
        self.assertEqual(base64.b64decode(images[0].data), b"image")
