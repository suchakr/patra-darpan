from __future__ import annotations

import base64
import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lib.retrieval_adapters import PassageStore, RetrievalError, RetrievalService, ZoektAdapter, json_bytes
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
                                          record={"source": {"sanchaya_repo": "https://github.com/cahcblr/sanchaya.git"}})
        service.entities = SimpleNamespace(_by_id={}, chunk_ids_for=lambda ids: set(), document_ids_for=lambda ids: set())
        service.catalog = SimpleNamespace(get_document=lambda doc: None)
        service.passages = SimpleNamespace(by_repo_path={}, by_id={})
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
    def test_vector_receives_original_query_and_prefiltered_scope(self, post):
        post.return_value = response([])
        service = self.service()
        service.vector.search.return_value = []
        service.passages.by_repo_path = {"Jyotisham/a.txt": [{"chunk_id": "a"}], "gretil/b.txt": [{"chunk_id": "b"}]}
        service.search("सूर्य", script_expansion="devanagari", file_filter="Jyo")
        service.vector.search.assert_called_once_with("सूर्य", limit=10, allowed_chunk_ids={"a"})
        self.assertIn("sūrya", post.call_args.kwargs["json"]["Q"])


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
