from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_retrieval_entity_release import build_candidate


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BuildEntityReleaseTests(unittest.TestCase):
    def _base_release(self, root: Path) -> Path:
        release_id = "base-release"
        releases = root / "releases"
        release_dir = releases / release_id
        release_dir.mkdir(parents=True)
        ontology = {
            "schema_version": "retrieval.ontology.v1",
            "ontology_id": "test",
            "version": "0.1.0",
            "entities": [],
        }
        payloads = {
            "input-manifest.json": b'{"sanchaya":{"commit":"' + b"a" * 40 + b'"}}\n',
            "retrieval-catalog.sqlite": b"catalog-snapshot",
            "corpus-manifest.jsonl": b'{"doc_id":"d1"}\n',
            "chunks.jsonl": b'{"chunk_id":"c1","document_id":"d1","repo_path":"p.md","logical_location":"p.1","content_sha256":"' + b"c" * 64 + b'","text":"Moon."}\n',
            "ontology.json": (json.dumps(ontology) + "\n").encode(),
            "vector-build.json": b'{"collection":"collection-1","dimensions":3,"chunk_count":1}\n',
            "entity-mentions.jsonl": b"",
            "entity-registry.jsonl": b"",
        }
        artifact_names = {
            "input-manifest.json": "input_manifest",
            "retrieval-catalog.sqlite": "retrieval_catalog",
            "corpus-manifest.jsonl": "corpus_manifest",
            "chunks.jsonl": "chunks",
            "ontology.json": "ontology_snapshot",
            "vector-build.json": "vector_build",
            "entity-mentions.jsonl": "entity_mentions",
            "entity-registry.jsonl": "entity_registry",
        }
        artifacts = {}
        for filename, payload in payloads.items():
            path = release_dir / filename
            path.write_bytes(payload)
            artifacts[artifact_names[filename]] = {
                "path": f"{release_id}/{filename}",
                "sha256": digest(path),
            }
        artifacts["lexical_index"] = {
            "backend": "zoekt",
            "repository": "sanchaya",
            "corpus_commit": "a" * 40,
        }
        artifacts["vector_index"] = {
            "backend": "qdrant",
            "collection": "collection-1",
            "dimensions": 3,
        }
        catalog_hash = artifacts["retrieval_catalog"]["sha256"]
        record = {
            "schema_version": "retrieval.release.v1",
            "release_id": release_id,
            "status": "ready",
            "created_at": "2026-01-01T00:00:00Z",
            "built_at": "2026-01-01T00:00:00Z",
            "source": {
                "sanchaya_repo": "https://example.invalid/sanchaya",
                "sanchaya_commit": "a" * 40,
                "patra_darpan_repo": "https://example.invalid/patra-darpan",
                "patra_darpan_commit": "b" * 40,
                "corpus_manifest_sha256": artifacts["corpus_manifest"]["sha256"],
                "catalog_revision": catalog_hash,
            },
            "pipeline": {
                "source_scope": {"paper_scope": "all", "sanchaya_scope": "test", "source_count": 1},
                "ontology": {"id": "test", "version": "0.1.0", "revision": "ontology.json"},
                "catalog": {"id": "test-catalog", "version": "v1", "revision": catalog_hash},
                "chunker": {"id": "test-chunker", "version": "v1"},
                "embedding": {"model": "test-model", "revision": "test", "dimensions": 3},
                "entity_extractor": {"id": "starter-gazetteer", "version": "starter-gazetteer-0.1.0"},
            },
            "artifacts": artifacts,
            "metrics": {
                "chunk_count": 1,
                "mention_count": 0,
                "entity_document_count": 0,
                "vector_point_count": 1,
            },
            "notes": "fixture",
        }
        (release_dir / "release.json").write_text(json.dumps(record), encoding="utf-8")
        (releases / "active-release.json").write_text(json.dumps(record), encoding="utf-8")
        return release_dir / "release.json"

    def test_builds_standalone_candidate_and_preserves_base_and_vector_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base_path = self._base_release(root)
            pointer_before = (base_path.parent.parent / "active-release.json").read_bytes()
            target = root / "ontology-v0.1.1.json"
            target.write_text(
                json.dumps({
                    "schema_version": "retrieval.ontology.v1",
                    "ontology_id": "test",
                    "version": "0.1.1",
                    "entities": [{
                        "id": "test:moon",
                        "type": "celestial_body",
                        "preferred_label": "Moon",
                        "aliases": ["Moon"],
                        "attributes": {},
                    }],
                }),
                encoding="utf-8",
            )

            candidate_path, result = build_candidate(
                base_release_path=base_path,
                ontology_path=target,
                output_root=root / "build-only",
                patra_darpan_commit="d" * 40,
            )

            self.assertTrue(candidate_path.is_file())
            self.assertEqual(result["mention_count"], 1)
            self.assertFalse((root / "build-only" / "active-release.json").exists())
            self.assertEqual(
                pointer_before,
                (base_path.parent.parent / "active-release.json").read_bytes(),
            )
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            self.assertEqual(candidate["pipeline"]["ontology"]["version"], "0.1.1")
            self.assertEqual(candidate["artifacts"]["vector_index"]["collection"], "collection-1")
            self.assertEqual(candidate["artifacts"]["chunks"]["sha256"],
                             json.loads(base_path.read_text(encoding="utf-8"))["artifacts"]["chunks"]["sha256"])
            self.assertTrue((base_path.parent / "entity-mentions.jsonl").read_bytes() == b"")

    def test_refuses_to_write_candidate_under_base_release_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base_path = self._base_release(root)
            target = root / "ontology-v0.1.1.json"
            target.write_text(
                json.dumps({"ontology_id": "test", "version": "0.1.1", "entities": []}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "refusing to stage"):
                build_candidate(
                    base_release_path=base_path,
                    ontology_path=target,
                    output_root=base_path.parent.parent,
                    release_id="candidate-release",
                    patra_darpan_commit="d" * 40,
                )


if __name__ == "__main__":
    unittest.main()
