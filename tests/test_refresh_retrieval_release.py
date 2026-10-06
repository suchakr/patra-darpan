from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/refresh_retrieval_release.py"
SPEC = importlib.util.spec_from_file_location("refresh_retrieval_release", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RefreshReleaseTests(unittest.TestCase):
    def test_rewrite_revision_changes_only_revision(self) -> None:
        rows = [{"chunk_id": "c1", "surface": "सूर्य", "corpus_revision": "old"}]

        rewritten = MODULE.rewrite_corpus_revision(
            rows, old_revision="old", new_revision="new", label="mention"
        )

        self.assertEqual(rewritten, [{"chunk_id": "c1", "surface": "सूर्य", "corpus_revision": "new"}])
        self.assertEqual(rows[0]["corpus_revision"], "old")

    def test_rewrite_revision_rejects_mixed_old_artifact(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected active release revision"):
            MODULE.rewrite_corpus_revision(
                [{"corpus_revision": "different"}],
                old_revision="old",
                new_revision="new",
                label="registry",
            )

    def test_source_hash_audit_uses_repository_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "patra-darpan" / "papers" / "one.md"
            source.parent.mkdir(parents=True)
            source.write_text("प्रमाण\n", encoding="utf-8")
            digest = MODULE.sha256_file(source)
            manifest = {
                "sources": [{"repo_path": "patra-darpan/papers/one.md", "content_sha256": digest}]
            }

            stats = MODULE.verify_selected_source_hashes(manifest, root)

        self.assertEqual(stats, {"source_count": 1, "hash_mismatch_count": 0})

    def test_chunk_inventory_digest_is_order_independent(self) -> None:
        rows = [
            {
                "chunk_id": "b",
                "content_sha256": "b" * 64,
                "repo_path": "b.md",
                "logical_location": "b",
            },
            {
                "chunk_id": "a",
                "content_sha256": "a" * 64,
                "repo_path": "a.md",
                "logical_location": "a",
            },
        ]

        self.assertEqual(MODULE.chunk_inventory_digest(rows), MODULE.chunk_inventory_digest(list(reversed(rows))))

    def test_release_id_replaces_the_previous_short_revision(self) -> None:
        self.assertEqual(
            MODULE.release_id_for_revision("retrieval-jyotisham-all-c6d35eb", "c6d35eb0", "0e5468e4"),
            "retrieval-jyotisham-all-0e5468e",
        )
        self.assertEqual(
            MODULE.release_id_for_revision("custom-release", "c6d35eb0", "0e5468e4"),
            "custom-release-refresh-0e5468e",
        )


if __name__ == "__main__":
    unittest.main()
