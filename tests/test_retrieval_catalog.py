from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from lib.retrieval_catalog import CatalogAdapter, build_retrieval_catalog


class RetrievalCatalogCoverageTests(unittest.TestCase):
    def _release(self, catalog: Path) -> SimpleNamespace:
        digest = hashlib.sha256(catalog.read_bytes()).hexdigest()
        test_case = self

        class Release(SimpleNamespace):
            def artifact_path(self, name: str) -> Path:
                test_case.assertEqual(name, "retrieval_catalog")
                return catalog

            def artifact_hash(self, name: str) -> str:
                test_case.assertEqual(name, "retrieval_catalog")
                return digest

        return Release(
            record={"artifacts": {"retrieval_catalog": {"path": "retrieval-catalog.sqlite"}}},
            corpus_revision="sanchaya-revision",
            catalog_revision=digest,
            release_id="test-release",
        )

    def test_catalog_keeps_full_metadata_and_marks_release_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            canonical = root / "canonical.sqlite"
            conn = sqlite3.connect(canonical)
            conn.executescript(
                """
                CREATE TABLE documents (
                    doc_id TEXT PRIMARY KEY,
                    title TEXT,
                    author_display TEXT,
                    year TEXT,
                    journal_label TEXT
                );
                CREATE TABLE asset_refs (asset_id INTEGER PRIMARY KEY, doc_id TEXT, asset_role TEXT, remote_url TEXT, local_rel_path TEXT, gcs_key TEXT);
                INSERT INTO documents VALUES ('paper-a', 'Indexed paper', 'R. N. Iyengar', '2024', 'IJHS');
                INSERT INTO documents VALUES ('paper-b', 'Metadata-only paper', 'R. N. Iyengar', '2023', 'IJHS');
                """
            )
            conn.commit()
            conn.close()
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "document_id": "pd:paper-a",
                                "source_kind": "patra-darpan",
                                "title": "Indexed paper",
                                "repo_path": "patra-darpan/papers/paper-a/document.md",
                            },
                            {
                                "document_id": "sanchaya:text-a",
                                "source_kind": "sanchaya",
                                "title": "Sanchaya text",
                                "repo_path": "Jyotisham/text-a.txt",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            catalog = root / "retrieval-catalog.sqlite"
            stats = build_retrieval_catalog(
                canonical,
                manifest,
                catalog,
                sanchaya_commit="sanchaya-revision",
            )
            self.assertEqual(stats["document_count"], 3)
            self.assertEqual(stats["indexed_document_count"], 2)
            adapter = CatalogAdapter(self._release(catalog))
            try:
                info = adapter.corpus_info()
                self.assertEqual(info["document_count"], 3)
                self.assertEqual(info["indexed_document_count"], 2)
                self.assertFalse(adapter.get_document("pd:paper-b")["indexed_in_release"])
                self.assertEqual(
                    len(adapter.search_documents("paper")["results"]),
                    2,
                )
                self.assertEqual(
                    len(adapter.search_documents("paper", indexed_in_release=True)["results"]),
                    1,
                )
                self.assertEqual(
                    len(adapter.author_works("R N Iyengar")["results"]),
                    2,
                )
                self.assertEqual(
                    len(adapter.author_works("R N Iyengar", indexed_in_release=True)["results"]),
                    1,
                )
            finally:
                adapter.close()


if __name__ == "__main__":
    unittest.main()
