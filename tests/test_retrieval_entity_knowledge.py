from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from lib.retrieval_adapters import (
    ENTITY_KNOWLEDGE_BYTE_LIMIT, ENTITY_LOOKUP_BYTE_LIMIT, ONTOLOGY_CONTEXT_BYTE_LIMIT,
    EntityAdapter, Release, RetrievalError, json_bytes,
)
from scripts.retrieval_mcp_server import build_mcp


def ontology_fixture():
    return {
        "ontology_id": "test", "version": "0.3.0",
        "entities": [
            {"id": "test:work", "type": "work", "preferred_label": "Śāstra",
             "aliases": ["शास्त्र", "Shastra"], "source_ref": "test-source",
             "curation_status": "corpus_candidate", "attributes": {"description": "A work"},
             "relations": [{"type": "authored_by", "target": "test:author"},
                           {"type": "composed_at", "target": "test:place"}]},
            {"id": "test:author", "type": "person", "preferred_label": "Author", "aliases": []},
            {"id": "test:place", "type": "place", "preferred_label": "Place", "aliases": []},
        ],
        "relations": [
            {"id": "r1", "type": "authored_by", "from": "test:work", "to": "test:author"},
            {"id": "r2", "type": "composed_at", "from": "test:work", "to": "test:place"},
        ],
    }


class EntityKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def adapter(self, ontology=None):
        ontology = ontology if ontology is not None else ontology_fixture()
        (self.root / "ontology.json").write_text(json.dumps(ontology), encoding="utf-8")
        registry = [{"entity_id": e["id"], "entity_type": e["type"],
                     "preferred_label": e["preferred_label"], "aliases": e.get("aliases", []),
                     "status": "seed", "mention_count": 37, "document_count": 2,
                     "document_ids": ["doc:a", "doc:b"], "corpus_revision": "revision"}
                    for e in ontology["entities"]]
        (self.root / "registry.jsonl").write_text("\n".join(json.dumps(r) for r in registry), encoding="utf-8")
        (self.root / "mentions.jsonl").write_text("", encoding="utf-8")
        release = Release(self.root / "active-release.json", {
            "release_id": "test", "source": {"sanchaya_commit": "revision"},
            "pipeline": {"ontology": {"id": "test", "version": "0.3.0"}},
            "artifacts": {"entity_registry": {"path": "registry.jsonl"},
                          "entity_mentions": {"path": "mentions.jsonl"}},
        })
        return EntityAdapter(release, self.root / "ontology.json")

    def test_exact_alias_keeps_identity_counts_and_returns_curated_knowledge(self):
        adapter = self.adapter()
        result = adapter.lookup("शास्त्र", limit=1)
        self.assertEqual(result["schema_version"], "retrieval.entity-lookup.v1")
        row = result["results"][0]
        self.assertEqual(row["entity_id"], "test:work")
        self.assertEqual((row["mention_count"], row["document_count"]), (37, 2))
        self.assertEqual(row["document_ids"], ["doc:a", "doc:b"])
        self.assertEqual(row["attributes"], {"description": "A work"})
        self.assertEqual(row["ontology"], {"id": "test", "version": "0.3.0"})
        self.assertEqual(row["source_ref"], "test-source")
        self.assertEqual(row["curation_status"], "corpus_candidate")
        self.assertFalse(row["knowledge_truncated"])
        self.assertTrue(row["relation_projection_consistent"])
        row["attributes"]["description"] = "changed by caller"
        self.assertEqual(adapter.lookup("Shastra")["results"][0]["attributes"]["description"], "A work")

    def test_incoming_authorship_does_not_assign_composition_location_to_author(self):
        adapter = self.adapter()
        author = adapter.lookup("Author")["results"][0]
        self.assertEqual(author["attributes"], {})
        self.assertEqual([(r["type"], r["direction"], r["target_preferred_label"])
                          for r in author["relations"]], [("authored_by", "incoming", "Śāstra")])
        related_work = adapter.lookup(author["relations"][0]["target_preferred_label"])["results"][0]
        site = next(r for r in related_work["relations"] if r["type"] == "composed_at")
        self.assertEqual((site["direction"], site["target_entity_id"], site["target_preferred_label"]),
                         ("outgoing", "test:place", "Place"))
        self.assertEqual((site["from_entity_id"], site["to_entity_id"]), ("test:work", "test:place"))

    def test_canonical_edges_win_and_stale_local_projection_is_flagged(self):
        ontology = ontology_fixture()
        ontology["entities"][0]["relations"] = [{"type": "invented", "target": "test:place"}]
        row = self.adapter(ontology).lookup("शास्त्र")["results"][0]
        self.assertFalse(row["relation_projection_consistent"])
        self.assertEqual({r["type"] for r in row["relations"]}, {"authored_by", "composed_at"})

    def test_unknown_relation_endpoint_is_rejected_and_release_version_check_remains(self):
        ontology = ontology_fixture()
        ontology["relations"][0]["to"] = "test:unknown"
        with self.assertRaisesRegex(RetrievalError, "unknown entity"):
            self.adapter(ontology)
        ontology = ontology_fixture()
        ontology["version"] = "0.4.0"
        with self.assertRaisesRegex(RetrievalError, "does not match active release"):
            self.adapter(ontology)

    def test_empty_knowledge_unknown_name_and_type_filter(self):
        ontology = ontology_fixture()
        ontology["relations"] = []
        for entity in ontology["entities"]:
            entity.pop("relations", None)
        adapter = self.adapter(ontology)
        row = adapter.lookup("Author")["results"][0]
        self.assertEqual((row["attributes"], row["relations"]), ({}, []))
        self.assertEqual(row["relation_count"], 0)
        self.assertFalse(row["knowledge_truncated"])
        self.assertEqual(adapter.lookup("missing")["total_results"], 0)
        self.assertEqual(adapter.lookup("Author", type_hint="work")["results"], [])

    def test_large_unicode_attributes_keep_whole_values_and_report_omissions(self):
        ontology = ontology_fixture()
        attributes = {"oversized": "अ" * 10000, "small": {"label": "पूर्ण"}}
        ontology["entities"][0]["attributes"] = attributes
        row = self.adapter(ontology).lookup("शास्त्र")["results"][0]
        self.assertEqual(row["attributes"], {"small": {"label": "पूर्ण"}})
        self.assertEqual(row["attribute_count"], 2)
        self.assertTrue(row["attributes_truncated"] and row["knowledge_truncated"])
        knowledge_keys = {"ontology", "source_ref", "curation_status", "attributes", "attribute_count",
                          "attributes_truncated", "relations", "relation_count", "relations_truncated",
                          "relation_projection_consistent", "knowledge_truncated"}
        self.assertLessEqual(json_bytes({k: row[k] for k in knowledge_keys}), ENTITY_KNOWLEDGE_BYTE_LIMIT)

    def test_many_relations_are_limited_without_partial_records(self):
        ontology = ontology_fixture()
        ontology["relations"] = []
        ontology["entities"][0]["relations"] = []
        for i in range(30):
            entity_id = f"test:place{i}"
            ontology["entities"].append({"id": entity_id, "type": "place", "preferred_label": f"Place {i}"})
            ontology["relations"].append({"id": f"edge{i}", "type": "composed_at", "from": "test:work", "to": entity_id})
            ontology["entities"][0]["relations"].append({"type": "composed_at", "target": entity_id})
        row = self.adapter(ontology).lookup("शास्त्र")["results"][0]
        self.assertEqual(row["relation_count"], 30)
        self.assertEqual(len(row["relations"]), 20)
        self.assertTrue(row["relations_truncated"] and row["knowledge_truncated"])
        self.assertTrue(all(r["target_preferred_label"] for r in row["relations"]))

    def test_lookup_byte_cap_and_result_limit_distinguish_incomplete_results(self):
        ontology = {"ontology_id": "test", "version": "0.3.0", "entities": [], "relations": []}
        for i in range(50):
            ontology["entities"].append({"id": f"test:item{i}", "type": "work", "preferred_label": f"Item {i}",
                                         "attributes": {"description": "अ" * 2400}})
        adapter = self.adapter(ontology)
        limited = adapter.lookup("Item", limit=1)
        self.assertEqual(limited["total_results"], 50)
        self.assertTrue(limited["results_truncated"])
        self.assertFalse(limited["byte_limit_reached"])
        large = adapter.lookup("Item", limit=50)
        self.assertGreater(len(large["results"]), 0)
        self.assertLess(len(large["results"]), 50)
        self.assertTrue(large["results_truncated"] and large["byte_limit_reached"])
        self.assertLessEqual(json_bytes(large), ENTITY_LOOKUP_BYTE_LIMIT)
        with self.assertRaisesRegex(RetrievalError, "metadata exceeds"):
            adapter.lookup("Item" * 30000)

    def test_context_keeps_discovery_fields_and_advertises_real_knowledge(self):
        adapter = self.adapter()
        context = adapter.ontology_context
        self.assertEqual(context["schema_version"], "retrieval.ontology-context.v1")
        self.assertEqual(context["entities"][0], {"id": "test:work", "type": "work",
                         "preferred_label": "Śāstra", "aliases": ["शास्त्र", "Shastra"]})
        self.assertEqual(context["knowledge_lookup"]["tool"], "lookup_entity")
        self.assertTrue(set(context["knowledge_lookup"]["fields"]) <= set(adapter.lookup("शास्त्र")["results"][0]))
        self.assertNotIn("relations", context["entities"][0])
        self.assertIn("not proof", " ".join(context["guidance"]))
        self.assertFalse(context["entities_truncated"])
        self.assertLessEqual(json_bytes(context), ONTOLOGY_CONTEXT_BYTE_LIMIT)

    def test_context_byte_limit_reports_an_omitted_large_vocabulary(self):
        ontology = ontology_fixture()
        ontology["entities"][1]["aliases"] = ["अ" * 30000]
        context = self.adapter(ontology).ontology_context
        self.assertTrue(context["entities_truncated"])
        self.assertEqual(context["entity_count"], 3)
        self.assertLess(len(context["entities"]), 3)
        self.assertLessEqual(json_bytes(context), ONTOLOGY_CONTEXT_BYTE_LIMIT)

    def test_mcp_schema_keeps_existing_arguments_and_allows_additive_results(self):
        adapter = self.adapter()
        server = build_mcp(SimpleNamespace(entities=adapter, release=adapter.release))
        tools = asyncio.run(server.list_tools())
        lookup = next(t for t in tools if t.name == "lookup_entity")
        self.assertEqual(set(lookup.inputSchema["properties"]), {"name", "type_hint", "limit"})
        self.assertEqual(lookup.inputSchema["required"], ["name"])
        self.assertEqual(lookup.outputSchema["type"], "object")
        self.assertIsNot(lookup.outputSchema.get("additionalProperties"), False)
        self.assertEqual(len(tools), 10)


if __name__ == "__main__":
    unittest.main()
