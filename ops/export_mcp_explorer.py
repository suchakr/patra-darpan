#!/usr/bin/env python3
"""Project the curated ontology for the static MCP Explorer; never read indexes."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ontology/jyotisha-v0.3.json"
OUTPUT = ROOT / "web/assets/data/mcp-ontology.json"


def projection(source: Path) -> dict:
    raw = source.read_bytes()
    ontology = json.loads(raw)
    ids = [entity["id"] for entity in ontology["entities"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate entity IDs")
    known = set(ids)
    relation_ids = set()
    relation_types = {row["id"] for row in ontology.get("relation_types", [])}
    for edge in ontology.get("relations", []):
        if edge["id"] in relation_ids:
            raise ValueError("Duplicate relation IDs")
        relation_ids.add(edge["id"])
        if edge["from"] not in known or edge["to"] not in known:
            raise ValueError(f"Unresolved relation endpoint: {edge['id']}")
        if edge["type"] not in relation_types:
            raise ValueError(f"Undeclared relation type: {edge['type']}")
    source_ref = source.name
    source_commit = None
    try:
        source_ref = source.relative_to(ROOT).as_posix()
        commit = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", source_ref],
            cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout.strip()
        if commit:
            committed = subprocess.run(
                ["git", "show", f"{commit}:{source_ref}"], cwd=ROOT,
                check=True, capture_output=True,
            ).stdout
            if committed == raw:
                source_commit = commit
    except (ValueError, OSError, subprocess.CalledProcessError):
        pass  # A local edited/untracked source must not claim a committed revision.
    fields = ("id", "type", "preferred_label", "aliases", "attributes",
              "source_ref", "curation_status", "comment")
    return {
        "schema_version": "mcp-explorer.ontology.v1",
        "ontology_id": ontology["ontology_id"],
        "version": ontology["version"],
        "status": ontology.get("status"),
        "source_file": source_ref,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_commit": source_commit,
        "entity_types": ontology.get("entity_types", []),
        "relation_types": ontology.get("relation_types", []),
        "sources": ontology.get("sources", []),
        "entities": [{key: entity[key] for key in fields if key in entity}
                     for entity in ontology["entities"]],
        "relations": ontology.get("relations", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ontology", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true", help="Fail if the static projection is stale")
    args = parser.parse_args()
    data = projection(args.ontology.resolve())
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != content:
            raise SystemExit("MCP Explorer projection is stale; run python3 ops/export_mcp_explorer.py")
        print("MCP Explorer projection matches its ontology source.")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(f"Projected v{data['version']}: {len(data['entities'])} entities, {len(data['relations'])} relations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
