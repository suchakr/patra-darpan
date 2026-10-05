from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ops.export_mcp_explorer import OUTPUT, ROOT, SOURCE, projection


class McpExplorerProjectionTests(unittest.TestCase):
    def test_checked_in_snapshot_matches_source_and_keeps_canonical_knowledge(self):
        actual = json.loads(OUTPUT.read_text(encoding="utf-8"))
        expected = projection(SOURCE)
        self.assertEqual(actual, expected)
        source = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(actual["relations"], source["relations"])
        self.assertEqual(len(actual["entities"]), len(source["entities"]))
        self.assertTrue(all("relations" not in entity for entity in actual["entities"]))
        dhani = next(entity for entity in actual["entities"] if entity["id"] == "jyotisha:nakshatra_dhanishtha")
        self.assertIn("श्रविष्ठा", dhani["aliases"])
        self.assertEqual(dhani["attributes"]["daivata"], "Vasu")

    def test_uncommitted_source_does_not_claim_a_git_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ontology.json"
            source.write_bytes(SOURCE.read_bytes())
            self.assertIsNone(projection(source)["source_commit"])

    def test_bad_endpoints_and_duplicate_ids_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ontology.json"
            data = json.loads(SOURCE.read_text(encoding="utf-8"))
            data["relations"][0]["to"] = "missing:entity"
            source.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "endpoint"):
                projection(source)
            data = json.loads(SOURCE.read_text(encoding="utf-8"))
            data["entities"].append(data["entities"][0])
            source.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate entity"):
                projection(source)

    def test_stale_projection_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "out.json"
            target.write_text("{}\n", encoding="utf-8")
            result = subprocess.run(["python3", str(ROOT / "ops/export_mcp_explorer.py"),
                                     "--output", str(target), "--check"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("stale", result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node required for browser graph core checks")
    def test_browser_core_preserves_search_graph_and_direction(self):
        subprocess.run(["node", str(ROOT / "tests/test_mcp_explorer_core.js")], check=True, cwd=ROOT)
