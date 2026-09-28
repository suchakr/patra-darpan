from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_corpus_metadata


class BuildCorpusMetadataAtomicTests(unittest.TestCase):
    def _write_catalog(self, path: Path, doc_id: str) -> dict[str, int]:
        conn = sqlite3.connect(path)
        try:
            conn.execute("CREATE TABLE documents (doc_id TEXT PRIMARY KEY)")
            conn.execute("INSERT INTO documents (doc_id) VALUES (?)", (doc_id,))
            conn.commit()
        finally:
            conn.close()
        return {"ijhs_rows": 1}

    def _document_ids(self, path: Path) -> list[str]:
        conn = sqlite3.connect(path)
        try:
            return [row[0] for row in conn.execute("SELECT doc_id FROM documents")]
        finally:
            conn.close()

    def test_failed_build_preserves_existing_catalog_and_cleans_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            destination = root / "spasta-corpus.sqlite"
            self._write_catalog(destination, "previous")
            previous_bytes = destination.read_bytes()

            def fail_after_partial_write(path: Path) -> dict[str, int]:
                self._write_catalog(path, "partial")
                raise RuntimeError("simulated source failure")

            with patch.object(
                build_corpus_metadata,
                "_populate_catalog",
                side_effect=fail_after_partial_write,
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated source failure"):
                    build_corpus_metadata.build_catalog_atomically(destination)

            self.assertEqual(destination.read_bytes(), previous_bytes)
            self.assertEqual(self._document_ids(destination), ["previous"])
            self.assertEqual(list(root.glob(".spasta-corpus.sqlite.*.tmp*")), [])

    def test_successful_build_replaces_catalog_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            destination = root / "spasta-corpus.sqlite"
            self._write_catalog(destination, "previous")

            with patch.object(
                build_corpus_metadata,
                "_populate_catalog",
                side_effect=lambda path: self._write_catalog(path, "new"),
            ):
                counts = build_corpus_metadata.build_catalog_atomically(destination)

            self.assertEqual(self._document_ids(destination), ["new"])
            self.assertEqual(counts, {"ijhs_rows": 1})
            self.assertEqual(list(root.glob(".spasta-corpus.sqlite.*.tmp*")), [])

    def test_invalid_candidate_does_not_replace_existing_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            destination = root / "spasta-corpus.sqlite"
            self._write_catalog(destination, "previous")
            previous_bytes = destination.read_bytes()

            def write_empty_catalog(path: Path) -> dict[str, int]:
                sqlite3.connect(path).close()
                return {"ijhs_rows": 0}

            with patch.object(
                build_corpus_metadata,
                "_populate_catalog",
                side_effect=write_empty_catalog,
            ):
                with self.assertRaisesRegex(sqlite3.DatabaseError, "documents table"):
                    build_corpus_metadata.build_catalog_atomically(destination)

            self.assertEqual(destination.read_bytes(), previous_bytes)
            self.assertEqual(self._document_ids(destination), ["previous"])
            self.assertEqual(list(root.glob(".spasta-corpus.sqlite.*.tmp*")), [])


if __name__ == "__main__":
    unittest.main()
