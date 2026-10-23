from __future__ import annotations

import base64
import importlib.util
import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from urllib3.exceptions import ReadTimeoutError

from lib.retrieval_adapters import PassageStore, RetrievalError, RetrievalService, ZoektAdapter, ZoektSearchError, json_bytes
from lib.retrieval_query import prepare_lexical_query, to_devanagari, from_devanagari


def match(line, offsets, *, filename=False, number=10):
    raw = line.encode("utf-8")
    return {"Line": base64.b64encode(raw).decode(), "LineNumber": number,
            "FileName": filename,
            "LineFragments": [{"LineOffset": len(line[:start].encode()),
                               "MatchLength": len(line[start:end].encode())} for start, end in offsets],
            "Before": base64.b64encode(("पूर्वम् " * 1000).encode()).decode(),
            "After": base64.b64encode(("पश्चात् " * 1000).encode()).decode()}


def file_row(path, matches):
    return {"Repository": "sanchaya", "FileName": path, "Version": "abc123", "LineMatches": matches}


def response(files, **stats):
    body = {"Result": {"Files": files, "FileCount": len(files),
                       "MatchCount": sum(len(m["LineFragments"]) for f in files for m in f["LineMatches"]),
                       "FilesSkipped": 0, "ShardsSkipped": 0, "Crashes": 0, **stats}}
    return raw_response(body)


def raw_response(body):
    result = Mock()
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    result.iter_content.return_value = [json.dumps(body).encode()]
    return result


class ScriptExpansionTests(unittest.TestCase):
    def test_roundtrip_sanskrit_with_clusters_signs_and_terminal_consonants(self):
        for dev, iast, hk in [("सूर्य", "sūrya", "sUrya"), ("श्रविष्ठा", "śraviṣṭhā", "zraviSThA"),
                              ("वाक्", "vāk", "vAk"), ("ऋतुः", "ṛtuḥ", "RtuH"),
                              ("अग्निं", "agniṃ", "agniM")]:
            with self.subTest(dev=dev):
                self.assertEqual(from_devanagari(dev, "iast"), iast)
                self.assertEqual(from_devanagari(dev, "harvard_kyoto"), hk)
                self.assertEqual(to_devanagari(iast, "iast"), dev)
                self.assertEqual(to_devanagari(hk, "harvard_kyoto"), dev)

    def test_raw_syntax_is_preserved_and_rich_expansion_rejected(self):
        raw = "file:Jyo type:filename सूर्य -file:gretil"
        self.assertEqual(prepare_lexical_query(raw)[0], raw)
        with self.assertRaises(ValueError):
            prepare_lexical_query(raw, script_expansion="devanagari")
        query, forms, _ = prepare_lexical_query("सूर्य", script_expansion="devanagari", file_filter="Vedic texts|Jyo")
        self.assertIn("sūrya", forms[0]["forms"])
        self.assertIn('file:"Vedic texts|Jyo"', query)

    def test_auto_does_not_guess_ascii_and_mixed_input_fails(self):
        _, forms, warnings = prepare_lexical_query("sun", script_expansion="auto")
        self.assertEqual(forms[0]["forms"], ["sun"])
        self.assertTrue(warnings)
        with self.assertRaises(ValueError):
            prepare_lexical_query("sūrya!", script_expansion="iast")
        _, forms, _ = prepare_lexical_query("Śraviṣṭhā", script_expansion="auto")
        self.assertIn("श्रविष्ठा", forms[0]["forms"])


class SearchPagingTests(unittest.TestCase):
    @patch("lib.retrieval_adapters.requests.post")
    def test_long_unicode_line_pages_every_match_without_duplicate_or_loss(self, post):
        line = "अ" * 6000 + "सूर्य" + "अ" * 6000 + "सूर्य" + "अ" * 6000
        offsets = [(6000, 6005), (12005, 12010)]
        post.return_value = response([file_row("Jyotisham/a.txt", [match(line, offsets)])])
        adapter = ZoektAdapter("http://zoekt:6070")
        page = adapter.search_page("सूर्य", match_limit=1, snippet_chars=100, context_lines=1)
        window = page["results"][0]["matches"][0]
        self.assertIn("सूर्य", window["line"])
        self.assertEqual(len(window["line"]), 100)
        self.assertTrue(window["context_truncated"])
        self.assertTrue(page["stats"]["counts_exact"])
        second = adapter.search_page("सूर्य", match_limit=1, snippet_chars=100, context_lines=1, cursor=page["next_cursor"])
        self.assertFalse(second["has_more"])
        self.assertNotEqual(window["match_start_byte"], second["results"][0]["matches"][0]["match_start_byte"])
        self.assertEqual(post.call_count, 1)
        self.assertLess(json_bytes(page), 4000)
        with self.assertRaises(RetrievalError):
            adapter.search_page("चन्द्र", snippet_chars=100, context_lines=1, cursor=page["next_cursor"])
        next(iter(adapter._snapshots.values()))["expires"] = time.monotonic() - 1
        with self.assertRaisesRegex(RetrievalError, "expired"):
            adapter.search_page("सूर्य", snippet_chars=100, context_lines=1, cursor=page["next_cursor"])

    @patch("lib.retrieval_adapters.requests.post")
    def test_backend_limit_is_not_reported_as_exact(self, post):
        post.return_value = response([file_row("a", [match("sun", [(0, 3)])])], FileCount=100, MatchCount=200)
        page = ZoektAdapter("http://zoekt").search_page("sun")
        self.assertEqual(page["stats"]["backend_match_count"], 200)
        self.assertFalse(page["stats"]["counts_exact"])
        self.assertTrue(page["stats"]["backend_display_limited"])
        post.return_value = response([file_row("a", [match("sun", [(0, 3)])])], FilesSkippedDueToCancellation=1)
        self.assertFalse(ZoektAdapter("http://zoekt").search_page("sun")["stats"]["counts_exact"])

    @patch("lib.retrieval_adapters.requests.post")
    def test_snapshot_cap_is_explicit_and_transport_is_bounded(self, post):
        post.return_value = response([file_row("a", [match("sun sun", [(0, 3), (4, 7)])])])
        adapter = ZoektAdapter("http://zoekt")
        adapter.MAX_WINDOWS = 1
        page = adapter.search_page("sun")
        self.assertTrue(page["stats"]["snapshot_limited"])
        self.assertFalse(page["stats"]["counts_exact"])
        post.return_value.iter_content.return_value = [b"x" * 100]
        adapter.MAX_RAW_BYTES = 10
        with self.assertRaisesRegex(RetrievalError, "exceeded"):
            adapter.search_page("another")


class ServiceTests(unittest.TestCase):
    def service(self):
        service = RetrievalService.__new__(RetrievalService)
        service.release = SimpleNamespace(corpus_revision="abc123", release_id="r", catalog_revision="cat",
                                          lexical_revision="declared-lexical",
                                          record={"source": {"sanchaya_repo": "https://github.com/cahcblr/sanchaya.git"},
                                                  "artifacts": {"lexical_index": {"backend": "zoekt",
                                                                                     "repository": "sanchaya",
                                                                                     "corpus_commit": "declared-lexical"}}})
        service.entities = SimpleNamespace(_by_id={}, chunk_ids_for=lambda ids: set(), document_ids_for=lambda ids: set(),
                                           coverage_info=lambda: {})
        service.catalog = SimpleNamespace(get_document=lambda doc: None, corpus_info=lambda: {})
        service.passages = SimpleNamespace(by_repo_path={}, by_id={}, chunks=[], by_document={})
        service.zoekt = ZoektAdapter("http://zoekt")
        service.vector = Mock()
        return service

    @patch("lib.retrieval_adapters.requests.post")
    def test_filename_query_is_lexical_and_has_a_link_without_content(self, post):
        name = "Jyotisham/surya siddhanta.txt"
        post.return_value = response([file_row(name, [match(name, [(0, len(name))], filename=True, number=0)])])
        service = self.service()
        result = service.search("file:Jyo type:filename सूर्य")
        service.vector.search.assert_not_called()
        self.assertEqual(result["mode"], "lexical")
        self.assertEqual(result["result_type"], "files")
        row = result["results"][0]
        self.assertIn("surya%20siddhanta.txt", row["source_url"])
        self.assertFalse(row["fetch_available"])
        self.assertTrue(row["matches"][0]["filename_match"])
        self.assertNotIn("before", row["matches"][0])

    @patch("lib.retrieval_adapters.requests.post")
    def test_search_reports_observed_lexical_revision_and_declared_split(self, post):
        post.return_value = response([file_row("Jyotisham/a.txt", [match("sun", [(0, 3)])])])
        service = self.service()

        result = service.search("sun", mode="lexical")

        self.assertEqual(result["corpus_revision"], "abc123")
        self.assertEqual(result["lexical_revision"], "abc123")
        self.assertEqual(result["lexical_revision_declared"], "declared-lexical")
        self.assertEqual(result["lexical_revision_source"], "zoekt_results")
        self.assertEqual(result["lexical_revisions_observed"], ["abc123"])
        self.assertIn("differs from the release-declared", result["warnings"][-1])
        self.assertEqual(result["results"][0]["lexical_revision"], "abc123")

    def test_corpus_info_exposes_declared_lexical_revision(self):
        info = self.service().get_corpus_info()

        self.assertEqual(info["indexes"]["lexical"]["revision"], "declared-lexical")
        self.assertEqual(info["indexes"]["lexical"]["revision_source"], "release_metadata")
        self.assertFalse(info["indexes"]["lexical"]["revision_verified"])

    @patch("lib.retrieval_adapters.requests.post")
    def test_vector_receives_original_query_and_prefiltered_scope(self, post):
        post.return_value = response([])
        service = self.service()
        service.vector.search.return_value = []
        service.passages.by_repo_path = {"Jyotisham/a.txt": [{"chunk_id": "a"}], "gretil/b.txt": [{"chunk_id": "b"}]}
        service.search("सूर्य", script_expansion="devanagari", file_filter="Jyo")
        service.vector.search.assert_called_once_with("सूर्य", limit=10, allowed_chunk_ids={"a"})
        self.assertIn("sūrya", post.call_args.kwargs["json"]["Q"])


class LexicalLimitsTests(unittest.TestCase):
    QUERY = "(धनिष्ठ|धनिष्ट|धनीष्ठ|dhaniṣṭ|dhanishta) -file:patra-darpan/papers"

    def service(self):
        return ServiceTests().service()

    @patch("lib.retrieval_adapters.requests.post")
    def test_budget_and_raw_query_preserved_with_protected_exclusions(self, post):
        post.return_value = response([])
        for raw in (self.QUERY, "(धनिष्ठ or dhanishta)", "(धनिष्ठ OR dhanishta)"):
            with self.subTest(query=raw):
                result = self.service().search(raw, mode="lexical", result_type="files", limit=1)
                payload = post.call_args.kwargs["json"]
                self.assertEqual(payload["Opts"]["MaxWallTime"], 5_000_000_000)
                self.assertEqual(post.call_args.kwargs["timeout"], (2.0, 10.0))
                self.assertEqual(result["lexical_query"], payload["Q"])
                self.assertIn(raw, payload["Q"])
                self.assertTrue(payload["Q"].endswith(" -file:patra-darpan/catalog/ -file:ontology/"))
                self.assertFalse(result["search_incomplete"])
                self.assertIsNone(result["lexical_error"])
                self.assertTrue(result["lexical_stats"]["counts_exact"])
                self.assertEqual(result["lexical_stats"]["backend_file_count"], 0)
        self.assertEqual(post.call_count, 3)  # No retries or automatic query rewriting.

    def test_budget_configuration_requires_headroom(self):
        for timeout, budget in ((5, 5), (4, 5), (10, 0), (10, -1), (float("inf"), 5), (10, float("nan"))):
            with self.subTest(timeout=timeout, budget=budget), self.assertRaises(RetrievalError):
                ZoektAdapter(timeout=timeout, search_timeout=budget)

    @patch("lib.retrieval_adapters.requests.post")
    def test_timeout_has_unknown_counts_safe_error_and_exact_submitted_query(self, post):
        post.side_effect = requests.ReadTimeout("private-backend:6070 secret details")
        result = self.service().search(self.QUERY, mode="lexical", result_type="files", limit=1)
        self.assertEqual(result["lexical_query"], post.call_args.kwargs["json"]["Q"])
        self.assertEqual(result["lexical_error"]["code"], "timeout")
        self.assertIn("lowercase 'or'", result["lexical_error"]["retry_hint"])
        self.assertTrue(result["search_incomplete"])
        self.assertEqual(result["lexical_stats"]["status"], "failed")
        self.assertIsNone(result["lexical_stats"]["backend_file_count"])
        self.assertIsNone(result["lexical_stats"]["backend_match_count"])
        self.assertFalse(result["lexical_stats"]["counts_exact"])
        self.assertEqual(result["results"], [])
        self.assertIsNone(result["next_cursor"])
        self.assertNotIn("private-backend", json.dumps(result))
        self.assertLess(json_bytes(result), 64000)
        self.assertEqual(post.call_count, 1)

    @patch("lib.retrieval_adapters.requests.post")
    def test_streamed_read_timeout_is_also_classified_as_timeout(self, post):
        post.return_value = response([])
        post.return_value.iter_content.side_effect = requests.ConnectionError(
            ReadTimeoutError(None, "/api/search", "read timed out"))
        result = self.service().search(self.QUERY, mode="lexical")
        self.assertEqual(result["lexical_error"]["code"], "timeout")
        self.assertIsNone(result["lexical_stats"]["backend_file_count"])

    @patch("lib.retrieval_adapters.requests.post")
    def test_transport_error_is_not_an_exact_zero(self, post):
        post.side_effect = requests.HTTPError("private upstream 503")
        result = self.service().search(self.QUERY, mode="lexical")
        self.assertEqual(result["lexical_error"]["code"], "transport_error")
        self.assertTrue(result["search_incomplete"])
        self.assertIsNone(result["lexical_stats"]["backend_match_count"])
        self.assertNotIn("private upstream", json.dumps(result))

    @patch("lib.retrieval_adapters.requests.post")
    def test_invalid_json_response_shape_and_backend_error_are_not_zero(self, post):
        for body, code in (([], "invalid_response"), ({}, "invalid_response"),
                           ({"Result": []}, "invalid_response"),
                           ({"Error": "private parser details"}, "backend_error")):
            with self.subTest(body=body):
                post.return_value = raw_response(body)
                result = self.service().search("sun", mode="lexical")
                self.assertEqual(result["lexical_error"]["code"], code)
                self.assertTrue(result["search_incomplete"])
                self.assertIsNone(result["lexical_stats"]["backend_file_count"])
                self.assertNotIn("private parser details", json.dumps(result))
        post.return_value.iter_content.return_value = [b"not JSON"]
        result = self.service().search("sun", mode="lexical")
        self.assertEqual(result["lexical_error"]["code"], "invalid_response")

    @patch("lib.retrieval_adapters.requests.post")
    def test_partial_snapshot_retains_hits_and_incompleteness_on_last_page(self, post):
        post.return_value = response([
            file_row("a.txt", [match("dhanishta", [(0, 8)])]),
            file_row("b.txt", [match("धनिष्ठ", [(0, 6)])])],
            FilesSkipped=611, ShardsSkipped=3, FlushReason=0, Duration=3_131_956_756)
        service = self.service()
        first = service.search(self.QUERY, mode="lexical", limit=1)
        self.assertEqual(len(first["results"]), 1)
        self.assertTrue(first["has_more"])
        self.assertIsNone(first["lexical_error"])
        self.assertTrue(first["search_incomplete"])
        self.assertEqual(first["lexical_stats"]["status"], "partial")
        self.assertTrue(first["lexical_stats"]["backend_work_limited"])
        self.assertFalse(first["lexical_stats"]["counts_exact"])
        self.assertAlmostEqual(first["lexical_stats"]["backend_duration_seconds"], 3.131956756)
        self.assertIn("Lexical search is incomplete", " ".join(first["warnings"]))
        last = service.search(self.QUERY, mode="lexical", limit=1, cursor=first["next_cursor"])
        self.assertFalse(last["has_more"])
        self.assertTrue(last["search_incomplete"])
        self.assertEqual(last["lexical_stats"], first["lexical_stats"])
        self.assertNotEqual(first["results"][0]["repo_path"], last["results"][0]["repo_path"])
        self.assertEqual(post.call_count, 1)

    @patch("lib.retrieval_adapters.requests.post")
    def test_empty_partial_response_does_not_establish_absence(self, post):
        for stats in ({"FilesSkipped": 1}, {"ShardsSkipped": 1},
                      {"FilesSkippedDueToCancellation": 1}, {"FlushReason": 1}, {"Crashes": 1}):
            with self.subTest(stats=stats):
                post.return_value = response([], **stats)
                result = self.service().search("sun", mode="lexical")
                self.assertEqual(result["results"], [])
                self.assertFalse(result["lexical_stats"]["counts_exact"])
                self.assertTrue(result["search_incomplete"])

    @patch("lib.retrieval_adapters.requests.post")
    def test_backend_result_with_error_keeps_hits_but_is_incomplete(self, post):
        post.return_value = raw_response({"Error": "private upstream detail", "Result": {
            "Files": [file_row("a.txt", [match("sun", [(0, 3)])])], "FileCount": 1, "MatchCount": 1}})
        result = self.service().search("sun", mode="lexical")
        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(result["lexical_stats"]["backend_reported_error"])
        self.assertTrue(result["search_incomplete"])
        self.assertNotIn("private upstream detail", json.dumps(result))

    @patch("lib.retrieval_adapters.requests.post")
    def test_hybrid_retains_vector_results_when_lexical_times_out(self, post):
        post.side_effect = requests.ReadTimeout()
        service = self.service()
        service.vector.search.return_value = [{"chunk_id": "a", "document_id": "d", "backend": "vector"}]
        result = service.search("sūrya", mode="hybrid", script_expansion="iast")
        service.vector.search.assert_called_once_with("sūrya", limit=10, allowed_chunk_ids=None)
        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(result["search_incomplete"])
        self.assertEqual(result["lexical_error"]["code"], "timeout")

    @patch("lib.retrieval_adapters.requests.post")
    def test_vector_only_does_not_claim_lexical_completeness(self, post):
        service = self.service()
        service.vector.search.return_value = []
        result = service.search("sun", mode="vector")
        post.assert_not_called()
        self.assertIsNone(result["search_incomplete"])
        self.assertIsNone(result["lexical_error"])
        self.assertIsNone(result["lexical_stats"])

    @patch("lib.retrieval_adapters.requests.post")
    def test_oversized_response_preserves_error_code(self, post):
        service = self.service()
        service.zoekt.MAX_RAW_BYTES = 1
        post.return_value = response([])
        result = service.search("sun", mode="lexical")
        self.assertEqual(result["lexical_error"]["code"], "response_too_large")
        self.assertTrue(result["search_incomplete"])


@unittest.skipUnless(importlib.util.find_spec("mcp"), "MCP SDK required for protocol tests")
class LexicalLimitsMCPTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, post, *, partial):
        from mcp.shared.memory import create_connected_server_and_client_session
        from scripts.retrieval_mcp_server import build_mcp

        service = ServiceTests().service()
        if partial:
            post.return_value = response([file_row("a.txt", [match("sun", [(0, 3)])])], ShardsSkipped=1)
        else:
            post.side_effect = requests.ReadTimeout()
        with patch.dict("os.environ", {"MCP_CATALOG_SQL_ENABLED": "false"}):
            server = build_mcp(service)
            async with create_connected_server_and_client_session(server) as client:
                tool = next(t for t in (await client.list_tools()).tools if t.name == "search_corpus")
                self.assertIn("lowercase 'or'", tool.description)
                self.assertIn("search_incomplete", tool.description)
                self.assertEqual(set(tool.inputSchema["properties"]), {
                    "query", "mode", "limit", "entity_ids", "result_type", "file_filter",
                    "script_expansion", "context_lines", "snippet_chars", "match_limit", "cursor"})
                guide = await client.read_resource("retrieval://search-guide")
                self.assertIn('lexical_stats.status="partial"', guide.contents[0].text)
                result = await client.call_tool("search_corpus", {"query": "sun", "mode": "lexical"})
                self.assertFalse(result.isError)
                body = result.structuredContent
                self.assertEqual(json.loads(result.content[0].text), body)
                self.assertTrue(body["search_incomplete"])
                self.assertEqual(body["lexical_query"], post.call_args.kwargs["json"]["Q"])
                self.assertLess(json_bytes(body), 64000)
                return body

    @patch("lib.retrieval_adapters.requests.post")
    async def test_partial_result_survives_mcp_serialization(self, post):
        result = await self.call(post, partial=True)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["lexical_stats"]["status"], "partial")

    @patch("lib.retrieval_adapters.requests.post")
    async def test_failed_counts_remain_null_through_mcp(self, post):
        result = await self.call(post, partial=False)
        self.assertEqual(result["lexical_error"]["code"], "timeout")
        self.assertIsNone(result["lexical_stats"]["backend_file_count"])


class PassagePagingTests(unittest.TestCase):
    def store(self):
        store = PassageStore.__new__(PassageStore)
        store.release = SimpleNamespace(corpus_revision="abc123", catalog_revision="c",
                                        record={"source": {"sanchaya_repo": "https://github.com/cahcblr/sanchaya.git"}})
        store.catalog = SimpleNamespace(get_document=lambda doc: {"source_refs": [{"uri": "https://example.org/paper.pdf"}]})
        rows = [{"chunk_id": str(i), "document_id": "d", "repo_path": "Jyotisham/a.txt", "text": "अ" * 5000} for i in range(25)]
        store.by_id = {row["chunk_id"]: row for row in rows}
        store.by_document = {"d": rows}
        store.by_repo_path = {"Jyotisham/a.txt": rows}
        return store

    def test_all_chunks_and_long_chunk_text_are_accessible(self):
        store = self.store()
        ids = []
        offset = 0
        while True:
            page = store.fetch(document_id="d", offset=offset, limit=20)
            self.assertLess(json_bytes(page), 64000)
            ids.extend(row["chunk_id"] for row in page["passages"])
            if not page["has_more"]:
                break
            offset = page["next_offset"]
        self.assertEqual(ids, [str(i) for i in range(25)])
        first = store.fetch(chunk_id="0")["passages"][0]
        second = store.fetch(chunk_id="0", text_offset=first["next_text_offset"])["passages"][0]
        self.assertEqual(first["text"] + second["text"], "अ" * 5000)
        self.assertEqual(second["citation_url"], "https://example.org/paper.pdf")
        self.assertIsNone(second["next_text_offset"])

    def test_batch_budget_reports_unprocessed_requests(self):
        result = self.store().fetch_many([{"chunk_id": str(i)} for i in range(25)])
        self.assertLess(json_bytes(result), 64000)
        self.assertTrue(result["response_limited"])
        self.assertEqual(result["next_request_index"], len(result["results"]))


class DeploymentTests(unittest.TestCase):
    def test_up_reuses_indexes_in_both_environments(self):
        import subprocess
        root = Path(__file__).resolve().parents[1]
        for env in (root / ".env", Path("/etc/patra-darpan/retrieval.env")):
            # -o skips validation only in this dry-run test; no services run.
            run = subprocess.run(["make", "-n", "-o", "check", "-o", "oauth-config", f"ENV_FILE={env}", "up"],
                                 cwd=root, capture_output=True, text=True, check=True)
            self.assertIn("build retrieval-mcp", run.stdout)
            self.assertIn("up -d retrieval-mcp-oauth", run.stdout)
            self.assertNotIn("build_retrieval_index", run.stdout)
            self.assertNotIn("create_retrieval_release", run.stdout)
            self.assertNotIn("retrieval-catalog-builder", run.stdout)


if __name__ == "__main__":
    unittest.main()
