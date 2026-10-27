from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import multiprocessing
from pathlib import Path
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lib.retrieval_catalog import CATALOG_SCHEMA, CatalogAdapter
from lib.retrieval_catalog_sql import (
    AUTHOR_ALIASES, BEARER_SQL_ID, CatalogSQLService, MAX_ROWS, WIRE_BUDGET,
    CatalogSQLError, _authorize, _private_identifier, _split_authors, mcp_envelope, token_identifier,
)


def fixture_catalog(root: Path, *, count: int = 2024, indexed: int = 150) -> CatalogAdapter:
    """Historical 080b5f6 coverage shape; synthetic records, not production evidence."""
    path = root / "catalog.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(CATALOG_SCHEMA)
    names = ["S Mahdihassan", "S. Mahadihassan", "A Author and B Author", "Iyengar, R N",
             None, "A Author, B Author", "Council of Scientific and Industrial Research",
             "Śrī Author", "A Author; B Author & C Author", "Unspecified et al."]
    for i in range(count + 34):
        pd = i < count
        raw_name = names[i] if i < len(names) else f"Researcher {i % 10}" if pd else None
        year = ["1980", "1981.0", None, "1965-1966"][i % 4] if pd else None
        role = ["portal_ijhs_metadata", "curated_pdf_metadata", "curated_link_metadata"][i % 3]
        conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            f"{'pd' if pd else 'sanchaya'}:{i:04d}", "patra-darpan" if pd else "sanchaya",
            str(i), f"Document {i:04d}", json.dumps([raw_name] if raw_name else [], ensure_ascii=False),
            year, "IJHS" if pd else None, json.dumps(["Astronomy", "Indic"] if i < indexed else []),
            f"papers/{i}/document.md" if i < indexed else None,
            json.dumps([{"role": role, "uri": "metadata://source.tsv"},
                        {"role": "primary_pdf", "uri": f"https://example.org/{i}.pdf"}] if pd else []),
            "hash" if i < indexed else None, int(i < indexed or not pd), "available", "fixture"))
    conn.execute("INSERT INTO catalog_info VALUES ('sanchaya_commit', '080b5f6')")
    conn.commit()
    conn.close()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    release = SimpleNamespace(
        record={"artifacts": {"retrieval_catalog": {"path": "catalog.sqlite"}}},
        corpus_revision="080b5f6", catalog_revision=digest, release_id="fixture-080b5f6",
        artifact_path=lambda _: path, artifact_hash=lambda _: digest)
    return CatalogAdapter(release)


class CatalogSQLTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.catalog = fixture_catalog(Path(self.temp.name))
        self.addCleanup(self.catalog.close)
        self.sql = CatalogSQLService(self.catalog, per_token_limit=200, global_limit=400)
        self.before = self.catalog.path.read_bytes()

    def query(self, sql, **kwargs):
        result = self.sql.query_catalog(sql, **kwargs)
        self.assertNotIn("error", result, result)
        return result

    def test_historical_fixture_counts_and_unknown_year_bucket(self):
        result = self.query("SELECT COUNT(*), SUM(indexed_in_release) FROM documents_v "
                            "WHERE source_kind='patra-darpan'")
        self.assertEqual(result["rows"], [[2024, 150]])
        years = self.query("SELECT year,COUNT(*) FROM documents_v WHERE source_kind='patra-darpan' "
                           "GROUP BY year ORDER BY year")["rows"]
        self.assertEqual(sum(row[1] for row in years), 2024)
        self.assertEqual(dict(years), {None: 1012, 1980: 506, 1981: 506})
        all_docs = self.query("SELECT SUM(document_count) FROM coverage_v")
        self.assertEqual(all_docs["rows"], [[2058]])
        self.assertEqual(self.catalog.path.read_bytes(), self.before)

    def test_one_call_author_aggregate_alias_and_distinct_coauthors(self):
        result = self.query("SELECT author_id,author_norm,COUNT(DISTINCT document_id) FROM authors_v "
                            "WHERE author_id IS NOT NULL GROUP BY author_id,author_norm "
                            "ORDER BY author_id")
        alias = [row for row in result["rows"] if row[0] == "author:s-mahdihassan"]
        self.assertEqual(alias, [["author:s-mahdihassan", "S Mahdihassan", 2]])
        for author in ("A Author", "B Author"):
            self.assertEqual(next(row[2] for row in result["rows"] if row[1] == author), 3)
        self.assertIn("Śrī Author", [row[1] for row in result["rows"]])

    def test_raw_names_positions_missing_and_ambiguous_are_preserved(self):
        rows = self.query("SELECT author_raw,author_name_raw,position,resolution_status,author_id "
                          "FROM authors_v WHERE document_id='pd:0002' ORDER BY position")["rows"]
        self.assertEqual([r[:4] for r in rows], [
            ["A Author and B Author", "A Author", 1, "unreviewed"],
            ["A Author and B Author", "B Author", 2, "unreviewed"]])
        ambiguous = self.query("SELECT author_norm,resolution_status FROM authors_v "
                               "WHERE document_id='pd:0003'")["rows"]
        self.assertEqual(ambiguous, [[None, "ambiguous"]])
        self.assertEqual(self.query("SELECT COUNT(*) FROM authors_v WHERE document_id='pd:0004'")["rows"], [[0]])
        self.assertTrue(_split_authors("Council of Scientific and Industrial Research")[1])
        self.assertTrue(_split_authors("Iyengar, R N")[1])
        self.assertTrue(_split_authors("IJHS")[1])
        self.assertTrue(_split_authors("ReviewReport")[1])
        self.assertEqual(_split_authors("A, B"), (["A", "B"], False))

    def test_schema_provenance_subject_caveats_and_examples(self):
        schema = self.sql.schema()
        self.assertEqual(set(schema["views"]), {"documents_v", "authors_v", "subjects_v", "coverage_v"})
        self.assertGreater(schema["known_issues"]["untagged_documents"], 0)
        self.assertGreater(schema["known_issues"]["ambiguous_author_occurrences"], 0)
        for example in schema["examples"]:
            self.query(example["sql"])
        collections = self.query("SELECT DISTINCT source_collection FROM documents_v ORDER BY source_collection")
        self.assertEqual(collections["rows"], [["curated-links"], ["curated-pdfs"], ["ijhs"], ["sanchaya"]])
        self.assertEqual(self.query("SELECT DISTINCT document_type FROM documents_v ORDER BY document_type")["rows"],
                         [["source_text"], ["unknown"]])

    def test_revisions_determinism_and_projection_changes(self):
        result = self.query("SELECT 1")
        self.assertEqual(result["sql"], "SELECT 1")
        self.assertEqual(result["catalog_revision"], hashlib.sha256(self.before).hexdigest())
        self.assertEqual(result["corpus_revision"], "080b5f6")
        self.assertEqual(result["release_id"], "fixture-080b5f6")
        self.assertEqual(CatalogSQLService(self.catalog).revisions, self.sql.revisions)
        with patch.dict(AUTHOR_ALIASES, {"different alias": ("author:new", "New Name")}):
            self.assertNotEqual(CatalogSQLService(self.catalog).revisions["analytics_revision"],
                                result["analytics_revision"])

    def test_missing_or_mismatched_catalogue_hash_fails_closed(self):
        with patch.object(self.catalog.release, "artifact_hash", return_value=None):
            with self.assertRaises(CatalogSQLError):
                CatalogSQLService(self.catalog)
        with patch.object(self.catalog.release, "catalog_revision", "different-revision"):
            with self.assertRaises(CatalogSQLError):
                CatalogSQLService(self.catalog)

    def test_writes_escapes_and_multiple_statements_rejected(self):
        attacks = [
            "DROP TABLE documents", "DELETE FROM documents_v", "UPDATE documents_v SET title='x'",
            "ATTACH DATABASE '/tmp/escape.sqlite' AS other", "PRAGMA database_list",
            "SELECT * FROM pragma_database_list", "SELECT load_extension('/tmp/evil')",
            "SELECT readfile('/etc/passwd')", "SELECT writefile('/tmp/a','x')",
            "SELECT * FROM documents", "SELECT * FROM _documents", "SELECT COUNT(*) FROM _documents",
            "SELECT * FROM sqlite_schema", "SELECT COUNT(*) FROM sqlite_master",
            "SELECT d.* FROM documents_v v JOIN _documents d ON 1=1",
            "WITH documents_v AS (SELECT * FROM _documents) SELECT * FROM documents_v",
            "WITH documents_v AS (SELECT * FROM \"_documents\") SELECT COUNT(*) FROM documents_v",
            "WITH 'documents_v' AS (SELECT * FROM '_documents') SELECT * FROM documents_v",
            "WITH documents_v AS (SELECT * FROM [_documents]) SELECT * FROM documents_v",
            "WITH documents_v AS (SELECT * FROM `_documents`) SELECT * FROM documents_v",
            "SELECT COUNT(*) FROM main.\"_documents\"",
            "WITH x AS (SELECT * FROM _authors) SELECT COUNT(*) FROM x",
            "SELECT 1; SELECT 2", "SELECT 1; DROP VIEW documents_v", "EXPLAIN SELECT 1",
            "SELECT randomblob(1000000000)", "SELECT sqlite_version()",
            "WITH x AS (SELECT 1) DELETE FROM documents_v",
        ]
        for sql in attacks:
            with self.subTest(sql=sql):
                self.assertIn("error", self.sql.query_catalog(sql))
        self.assertEqual(self.catalog.path.read_bytes(), self.before)
        self.assertEqual(self.query("SELECT COUNT(*) FROM documents_v")["rows"], [[2058]])

    def test_select_cte_join_comments_and_semicolon_literals_accepted(self):
        result = self.query("/* harmless */ -- comment\n WITH x AS (SELECT document_id FROM documents_v) "
                            "SELECT COUNT(*) FROM x JOIN authors_v USING(document_id)")
        self.assertGreater(result["rows"][0][0], 0)
        self.assertEqual(self.query("SELECT '; DROP TABLE x;' AS harmless;")["rows"], [["; DROP TABLE x;"]])

    def test_sqlite_346_and_350_optimized_count_callback_variants(self):
        # Production 3.46 omits the database name; macOS 3.50 supplies "main".
        # This callback is safe only after the separate private-identifier gate.
        for database in (None, "main"):
            self.assertEqual(_authorize(sqlite3.SQLITE_READ, "_documents", "", database, None),
                             sqlite3.SQLITE_OK)
        for table, column, database in (("_documents", "title", None), ("sqlite_schema", "", None),
                                        ("_documents", "", "other")):
            self.assertEqual(_authorize(sqlite3.SQLITE_READ, table, column, database, None),
                             sqlite3.SQLITE_DENY)
        for sql in ("SELECT COUNT(*) FROM _documents", "SELECT COUNT(*) FROM main.\"_documents\"",
                    "WITH documents_v AS (SELECT * FROM [_documents]) SELECT COUNT(*) FROM documents_v"):
            self.assertTrue(_private_identifier(sql))
            self.assertIn("error", self.sql.query_catalog(sql))

    def test_row_limit_detects_truncation_without_claiming_total(self):
        result = self.query("SELECT document_id FROM documents_v ORDER BY document_id", max_rows=2)
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["truncation_reason"], "max_rows")
        self.assertTrue(result["truncated"])
        result = self.query("SELECT document_id FROM documents_v ORDER BY document_id LIMIT 2", max_rows=2)
        self.assertFalse(result["truncated"])
        self.assertEqual(result["row_count"], 2)

    def test_unicode_byte_limit_covers_complete_mcp_envelope(self):
        result = self.query("SELECT '" + "अ" * 300 + "' AS title FROM documents_v", max_rows=MAX_ROWS)
        self.assertEqual(result["truncation_reason"], "response_bytes")
        self.assertLess(len(result["rows"]), MAX_ROWS)
        self.assertLessEqual(len(json.dumps(mcp_envelope(result), ensure_ascii=False,
                                            separators=(",", ":")).encode()), WIRE_BUDGET)
        self.assertTrue(all(row == ["अ" * 300] for row in result["rows"]))

    def test_large_computed_cells_invalid_numbers_and_validation(self):
        # A huge group_concat is bounded inside SQLite, before serialization.
        result = self.sql.query_catalog("SELECT group_concat(title || title || title) FROM documents_v")
        self.assertIn("error", result)
        self.assertIn("error", self.sql.query_catalog("SELECT 1e999"))
        for limit in (0, -1, MAX_ROWS + 1, True, 2.5):
            self.assertEqual(self.sql.query_catalog("SELECT 1", max_rows=limit)["error"]["code"], "invalid_limit")
        self.assertEqual(self.sql.query_catalog("SELECT '" + "अ" * 3000 + "'")["error"]["code"], "invalid_query")
        self.assertEqual(self.sql.query_catalog("SELECT '" + "अ" * 3000 + "'")["sql"], "")
        self.assertEqual(self.sql.query_catalog("\ud800")["error"]["code"], "invalid_query")
        escaped = self.sql.query_catalog("SELECT '" + "\x01" * 8000 + "'")
        self.assertEqual(escaped["error"]["code"], "invalid_query")
        self.assertEqual(escaped["sql"], "")
        self.assertLess(len(json.dumps(mcp_envelope(escaped)).encode()), 64000)

    def test_expensive_aggregate_timeout_cleanup_and_recovery(self):
        self.sql.deadline_seconds = 0.6
        before = {p.pid for p in multiprocessing.active_children()}
        start = time.monotonic()
        result = self.sql.query_catalog("SELECT COUNT(*) FROM documents_v a CROSS JOIN documents_v b "
                                  "CROSS JOIN documents_v c")
        self.assertEqual(result["error"]["code"], "timeout", result)
        self.assertLess(time.monotonic() - start, 2.0)
        self.assertEqual(result["rows"], [])
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)
        self.sql.deadline_seconds = 5
        self.assertEqual(self.query("SELECT COUNT(*) FROM documents_v")["rows"], [[2058]])

    def test_recursive_query_timeout(self):
        self.sql.deadline_seconds = 0.6
        result = self.sql.query_catalog("WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x) "
                                  "SELECT SUM(n) FROM x")
        self.assertEqual(result["error"]["code"], "timeout", result)

    def test_rate_limits_identity_isolation_global_cap_and_expiry(self):
        service = CatalogSQLService(self.catalog, per_token_limit=1, global_limit=2)
        # Invalid queries consume quota too, without spawning workers.
        self.assertEqual(service.query_catalog("DROP TABLE x", token_id="a")["error"]["code"], "query_rejected")
        self.assertEqual(service.query_catalog("SELECT 1", token_id="a")["error"]["code"], "rate_limited")
        self.assertEqual(service.query_catalog("DROP TABLE x", token_id="b")["error"]["code"], "query_rejected")
        self.assertEqual(service.query_catalog("SELECT 1", token_id="c")["error"]["code"], "rate_limited")
        with patch("lib.retrieval_catalog_sql.time.monotonic", return_value=time.monotonic() + 61):
            self.assertTrue(service._admit("a"))

    def test_concurrency_is_bounded_and_logs_never_include_credentials_or_rows(self):
        service = CatalogSQLService(self.catalog, concurrency=1)
        service._slots.acquire()
        try:
            self.assertEqual(service.query_catalog("SELECT 1")["error"]["code"], "busy")
        finally:
            service._slots.release()
        credential = "private-bearer-value"
        with self.assertLogs("retrieval.catalog_sql", level="INFO") as logs:
            service.query_catalog("SELECT 'unlogged-result'", token_id=token_identifier(credential))
        self.assertNotIn(credential, "".join(logs.output))
        logged = json.loads(logs.records[0].message)
        self.assertEqual(set(logged), {"sql", "token_id", "outcome", "elapsed_ms", "row_count"})
        self.assertNotIn("rows", logged)
        self.assertEqual(len(logged["token_id"]), 24)


@unittest.skipUnless(importlib.util.find_spec("mcp"), "MCP SDK required for protocol tests")
class CatalogSQLMCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.catalog = fixture_catalog(Path(self.temp.name), count=12, indexed=3)
        self.addCleanup(self.catalog.close)
        self.service = SimpleNamespace(catalog=self.catalog, release=self.catalog.release,
                                       entities=SimpleNamespace(ontology_context={}))
        quiet = patch("lib.retrieval_catalog_sql.LOG.info")
        quiet.start()
        self.addCleanup(quiet.stop)

    async def test_real_mcp_client_session_schema_query_and_rejection(self):
        from mcp.shared.memory import create_connected_server_and_client_session
        from scripts.retrieval_mcp_server import build_mcp
        with patch.dict("os.environ", {"MCP_CATALOG_SQL_ENABLED": "true", "MCP_TRANSPORT": "stdio"}):
            server = build_mcp(self.service)
            async with create_connected_server_and_client_session(server) as client:
                tools = await client.list_tools()
                self.assertEqual(len(tools.tools), 11)
                tool_names = {tool.name for tool in tools.tools}
                self.assertIn("query_catalog", tool_names)
                self.assertNotIn("run_sql", tool_names)
                schema_result = await client.read_resource("retrieval://catalog-schema")
                schema = json.loads(schema_result.contents[0].text)
                result = await client.call_tool("query_catalog", {"query": "SELECT COUNT(*) FROM documents_v"})
                self.assertFalse(result.isError)
                self.assertEqual(result.structuredContent["rows"], [[46]])
                self.assertEqual(result.structuredContent["catalog_revision"], schema["catalog_revision"])
                rejected = await client.call_tool("query_catalog", {"query": "SELECT load_extension('bad')"})
                self.assertTrue(rejected.isError)

    async def test_surface_default_off_and_enabled_schema_examples(self):
        from scripts.retrieval_mcp_server import build_mcp
        with patch.dict("os.environ", {"MCP_CATALOG_SQL_ENABLED": "false"}):
            server = build_mcp(self.service)
            self.assertEqual(len(await server.list_tools()), 10)
            self.assertNotIn("retrieval://catalog-schema", [str(r.uri) for r in await server.list_resources()])
        with patch.dict("os.environ", {"MCP_CATALOG_SQL_ENABLED": "true"}):
            server = build_mcp(self.service)
            tools = await server.list_tools()
            self.assertEqual(len(tools), 11)
            tool_names = {t.name for t in tools}
            self.assertNotIn("run_sql", tool_names)
            tool = next(t for t in tools if t.name == "query_catalog")
            self.assertEqual(set(tool.inputSchema["properties"]), {"query", "max_rows"})
            self.assertEqual(
                tool.description,
                "Read-only SQL over the document catalogue (metadata aggregates). "
                "Not for passage search; use search_corpus.",
            )
            resources = await server.read_resource("retrieval://catalog-schema")
            schema = json.loads(list(resources)[0].content)
            self.assertIn("known_issues", schema)
            self.assertEqual(schema["query_tool"]["name"], "query_catalog")
            self.assertIn("query", schema["query_tool"]["parameters"])
            identity = BEARER_SQL_ID.set(token_identifier("test-token"))
            try:
                for example in schema["examples"]:
                    response = await server.call_tool("query_catalog", {"query": example["sql"]})
                    self.assertFalse(response.isError, response)
                    self.assertIn("catalog_revision", response.structuredContent)
                    self.assertEqual(json.loads(response.content[0].text), response.structuredContent)
            finally:
                BEARER_SQL_ID.reset(identity)

    async def test_bearer_auth_context_is_set_only_after_validation_and_reset(self):
        from scripts.retrieval_mcp_server import BearerAuthMiddleware
        seen = []

        async def app(scope, receive, send):
            seen.append(BEARER_SQL_ID.get())
            await asyncio.sleep(0)
            self.assertEqual(BEARER_SQL_ID.get(), seen[-1])

        async def receive():
            return {}

        async def send(_message):
            pass

        protected = BearerAuthMiddleware(app, "credential")
        await protected({"type": "http", "headers": [(b"authorization", b"Bearer wrong")]}, receive, send)
        self.assertEqual(seen, [])
        await protected({"type": "http", "headers": [(b"authorization", b"Bearer credential")]}, receive, send)
        self.assertEqual(seen, [token_identifier("credential")])
        self.assertIsNone(BEARER_SQL_ID.get())

    async def test_unauthenticated_sql_fails_closed_and_local_opt_out_is_explicit(self):
        from scripts.retrieval_mcp_server import build_mcp
        with patch.dict("os.environ", {"MCP_CATALOG_SQL_ENABLED": "true", "MCP_AUTH_REQUIRED": "true",
                                       "MCP_TRANSPORT": "streamable-http"}):
            server = build_mcp(self.service)
            response = await server.call_tool("query_catalog", {"query": "SELECT 1"})
            self.assertTrue(response.isError)
            self.assertEqual(response.structuredContent["error"]["code"], "authentication_required")
        with patch.dict("os.environ", {"MCP_CATALOG_SQL_ENABLED": "true", "MCP_TRANSPORT": "stdio"}):
            server = build_mcp(self.service)
            response = await server.call_tool("query_catalog", {"query": "SELECT 1"})
            self.assertEqual(response.structuredContent["rows"], [[1]])

    async def test_oauth_verified_identity_and_actual_response_byte_limit(self):
        from mcp.server.auth.middleware.auth_context import auth_context_var
        from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
        from mcp.server.auth.provider import AccessToken
        from scripts.retrieval_mcp_server import build_mcp
        # build_mcp installs real provider routes for a configured provider. A minimal
        # SDK-compatible provider suffices here; no Google/HTTP requests are made.
        from lib.retrieval_oauth import EmailAllowlist, GoogleOAuthProvider, OAuthStateStore
        root = Path(self.temp.name)
        allowlist = root / "allowlist.txt"
        allowlist.write_text("test@example.org\n", encoding="utf-8")
        provider = GoogleOAuthProvider(
            issuer_url="https://example.org", resource_url="https://example.org/mcp",
            redirect_uri="https://example.org/oauth/callback", google_client_id="test",
            google_client_secret="test-secret", allowlist=EmailAllowlist(allowlist),
            state_store=OAuthStateStore(root / "oauth.sqlite"))
        with patch.dict("os.environ", {"MCP_CATALOG_SQL_ENABLED": "true"}):
            server = build_mcp(self.service, oauth_provider=provider)
            denied = await server.call_tool("query_catalog", {"query": "SELECT 1"})
            self.assertTrue(denied.isError)
            access = AccessToken(token="oauth-private-token", client_id="client", scopes=["mcp"])
            context = auth_context_var.set(AuthenticatedUser(access))
            try:
                result = await server.call_tool("query_catalog", {"query": "SELECT '" + "अ" * 1000 +
                                                           "' FROM documents_v", "max_rows": 1000})
                self.assertFalse(result.isError, result)
                self.assertTrue(result.structuredContent["truncated"])
                self.assertLess(len(result.model_dump_json().encode()), 64000)
                rejected = await server.call_tool("query_catalog", {"query": "SELECT * FROM _documents"})
                self.assertTrue(rejected.isError)
            finally:
                auth_context_var.reset(context)


if __name__ == "__main__":
    unittest.main()
