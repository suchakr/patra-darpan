#!/usr/bin/env python3
"""Create v0.4 from v0.3.1 and only the reviewed provisional batch items."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.retrieval_entities import load_alias_targets

ALLOWED_SOURCE_STATUSES = {"candidate", "rejected", "provisional", "approved"}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def promote(
    base: dict[str, Any], proposal: dict[str, Any], *, expected_items: int = 39,
    proposal_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    if str(base.get("version")) != "0.3.1":
        raise ValueError("v0.4 must be based on ontology version 0.3.1")
    entities = base.get("entities")
    if not isinstance(entities, list):
        raise ValueError("base ontology has no entity list")
    by_id = {str(entity.get("id") or ""): entity for entity in entities}
    if len(by_id) != len(entities) or "" in by_id:
        raise ValueError("base ontology entity IDs must be present and unique")

    result = copy.deepcopy(base)
    result_by_id = {str(entity["id"]): entity for entity in result["entities"]}
    provisional: list[tuple[str, str, dict[str, Any]]] = []
    seen: set[tuple[str, str, str]] = set()
    for entity_id, proposal_entity in proposal.items():
        if entity_id == "_meta":
            continue
        if entity_id not in by_id or not isinstance(proposal_entity, dict):
            raise ValueError(f"proposal references unknown or malformed entity: {entity_id}")
        for field, kind in (("contextual_synonyms", "synonym"), ("spelling_variants", "variant")):
            entries = proposal_entity.get(field) or []
            if not isinstance(entries, list):
                raise ValueError(f"{entity_id}.{field} must be a list")
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError(f"{entity_id}.{field} contains a non-object item")
                status = entry.get("status")
                if status not in ALLOWED_SOURCE_STATUSES:
                    raise ValueError(f"unsupported review status {status!r} for {entity_id}.{field}")
                if status != "provisional":
                    continue
                form = str(entry.get("form") or "").strip()
                if not form:
                    raise ValueError(f"provisional item has no form: {entity_id}.{field}")
                key = (entity_id, kind, form)
                if key in seen:
                    raise ValueError(f"duplicate provisional item: {entity_id} {form!r}")
                seen.add(key)
                provisional.append((entity_id, kind, copy.deepcopy(entry)))

    if len(provisional) != expected_items:
        raise ValueError(f"expected {expected_items} provisional items, found {len(provisional)}")

    counts = {"contextual_synonyms": 0, "spelling_variants": 0}
    per_entity: dict[str, dict[str, int]] = {}
    for entity_id, kind, entry in provisional:
        entity = result_by_id[entity_id]
        attributes = entity.setdefault("attributes", {})
        if not isinstance(attributes, dict):
            raise ValueError(f"{entity_id}.attributes must be an object")
        form = entry["form"].strip()
        if kind == "synonym":
            field = "contextual_synonyms"
            values = attributes.setdefault(field, [])
            if not isinstance(values, list):
                raise ValueError(f"{entity_id}.{field} must be a list")
            if any(str(row.get("form") or "") == form for row in values if isinstance(row, dict)):
                raise ValueError(f"contextual synonym already exists: {entity_id} {form!r}")
            values.append(entry)
            counts["contextual_synonyms"] += 1
            per_entity.setdefault(entity_id, {"synonyms": 0, "variants": 0})["synonyms"] += 1
        else:
            field = "variant_evidence"
            values = attributes.setdefault(field, [])
            if not isinstance(values, list):
                raise ValueError(f"{entity_id}.{field} must be a list")
            if any(str(row.get("form") or "") == form for row in values if isinstance(row, dict)):
                raise ValueError(f"spelling-variant evidence already exists: {entity_id} {form!r}")
            values.append(entry)
            aliases = entity.setdefault("aliases", [])
            if not isinstance(aliases, list):
                raise ValueError(f"{entity_id}.aliases must be a list")
            if form not in aliases:
                aliases.append(form)
            counts["spelling_variants"] += 1
            per_entity.setdefault(entity_id, {"synonyms": 0, "variants": 0})["variants"] += 1

    for entity_id, item_counts in per_entity.items():
        entity = result_by_id[entity_id]
        changes = entity.setdefault("v04_changes", [])
        if not isinstance(changes, list):
            raise ValueError(f"{entity_id}.v04_changes must be a list")
        changes.append(
            "v0.4.0 adds "
            f"{item_counts['synonyms']} provisional contextual synonym(s) and "
            f"{item_counts['variants']} provisional spelling variant(s) from the reviewed batch; "
            "provisional is not expert approval."
        )

    result["version"] = "0.4.0"
    result["label"] = "Jyotiṣa ontology v0.4.0"
    result["artifact_role"] = "provisional_candidate"
    result["generation"] = copy.deepcopy(result.get("generation") or {})
    generation = result["generation"]
    generation["input_artifact"] = "ontology/jyotisha-v0.3.1.json"
    generation["v04_reviewed_proposal"] = {
        "path": "agent-handoffs/patra-darpan-mcp/batches/012-claude-attachments/proposal-reviewed.json",
        "sha256": proposal_sha256 or hashlib.sha256(
            json.dumps(proposal, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "selection": "only items with status=provisional; candidate and rejected records are not copied",
        "item_count": len(provisional),
        **counts,
    }
    validation = generation.setdefault("validation", {})
    validation["v04_provisional_item_count"] = len(provisional)
    validation["v04_provisional_contextual_synonyms"] = counts["contextual_synonyms"]
    validation["v04_provisional_spelling_variants"] = counts["spelling_variants"]
    sources = result.setdefault("sources", [])
    source_id = "proposal_reviewed_batch_012"
    if any(row.get("id") == source_id for row in sources if isinstance(row, dict)):
        raise ValueError(f"source ID already exists: {source_id}")
    sources.append({
        "id": source_id,
        "path": "agent-handoffs/patra-darpan-mcp/batches/012-claude-attachments/proposal-reviewed.json",
        "description": "Reviewed candidate source for 39 provisional Jyotiṣa names; copied as provisional pilot data, not expert approval.",
    })

    base_targets, _ = load_alias_targets(base)
    targets, alias_summary = load_alias_targets(result)
    base_collision_count = sum(len({target.entity_id for target in rows}) > 1 for rows in base_targets.values())
    collision_count = sum(len({target.entity_id for target in rows}) > 1 for rows in targets.values())
    if collision_count > base_collision_count:
        raise ValueError(
            f"provisional aliases introduce cross-entity collisions: {base_collision_count} -> {collision_count}"
        )
    validation.update({
        "explicit_alias_entries": sum(len(entity.get("aliases") or []) for entity in result["entities"]),
        "unique_normalized_aliases_including_preferred_labels": alias_summary["alias_count"],
        "cross_entity_alias_collisions": collision_count,
        "ambiguous_alias_entries": alias_summary["ambiguous_alias_count"],
    })
    return result, {"items": len(provisional), **counts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=ROOT / "ontology/jyotisha-v0.3.1.json")
    parser.add_argument("--reviewed-proposal", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "ontology/jyotisha-v0.4.0.json")
    parser.add_argument("--force", action="store_true", help="replace the generated output file")
    args = parser.parse_args()
    if args.output.exists() and not args.force:
        raise FileExistsError(f"refusing to overwrite existing ontology: {args.output}")
    proposal_bytes = args.reviewed_proposal.read_bytes()
    output, counts = promote(
        load_object(args.base),
        json.loads(proposal_bytes.decode("utf-8")),
        proposal_sha256=hashlib.sha256(proposal_bytes).hexdigest(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "version": output["version"], **counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
