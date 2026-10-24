#!/usr/bin/env python3
"""Compare entity mention counts for ambiguity markers and provisional variants.

All ontology versions are evaluated against the same pinned chunk inventory.
Contextual synonyms are deliberately excluded: only aliases (including
provisional variant_evidence entries) create extractor mentions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.retrieval_entities import iter_mentions, load_alias_targets, read_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, required=True, help="pinned chunk JSONL")
    parser.add_argument("--corpus-revision", required=True, help="source commit for the chunk inventory")
    parser.add_argument("--release-id", required=True, help="release identifier for the pinned chunk inventory")
    parser.add_argument(
        "--base-ontology", type=Path, default=ROOT / "ontology" / "jyotisha-v0.3.json"
    )
    parser.add_argument(
        "--target-ontology", type=Path, default=ROOT / "ontology" / "jyotisha-v0.3.1.json"
    )
    parser.add_argument("--provisional-ontology", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None, help="Markdown report path; defaults to stdout")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def norm(value: str, *, casefold: bool) -> str:
    value = unicodedata.normalize("NFC", value).replace("\u00a0", " ")
    return value.casefold() if casefold else value


def normalizer(ontology: dict[str, Any]):
    config = ontology.get("normalization") or {}
    casefold = bool(config.get("latin_casefold", True))
    return lambda value: norm(value, casefold=casefold)


def mentions_for(chunks: list[dict[str, Any]], ontology: dict[str, Any], revision: str) -> list[dict[str, Any]]:
    # Validate aliases and ambiguity markers before doing the corpus pass.
    load_alias_targets(ontology)
    return list(iter_mentions(chunks, ontology, corpus_revision=revision))


def keyed_rows(mentions: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in mentions:
        entity_id = row.get("canonical_entity_id")
        if entity_id:
            result.setdefault((str(entity_id), str(row.get("normalized_form") or "")), []).append(row)
    return result


def assessment(rows: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    flagged = sum(row.get("ambiguous") is True for row in rows)
    unflagged = sum(row.get("ambiguous") is False for row in rows)
    return len(rows), flagged, unflagged, len(rows) - flagged - unflagged


def marked_forms(ontology: dict[str, Any]) -> list[tuple[str, str, str]]:
    result = []
    for entity in ontology.get("entities") or []:
        for entry in (entity.get("attributes") or {}).get("ambiguous_aliases") or []:
            result.append((str(entity["id"]), str(entry["form"]), str(entity.get("preferred_label") or "")))
    return result


def provisional_variants(ontology: dict[str, Any]) -> list[tuple[str, str, str]]:
    result = []
    canonicalize = normalizer(ontology)
    for entity in ontology.get("entities") or []:
        attrs = entity.get("attributes") or {}
        aliases = {canonicalize(str(value)) for value in entity.get("aliases") or []}
        for entry in attrs.get("variant_evidence") or []:
            if entry.get("status") != "provisional":
                continue
            form = str(entry.get("form") or "").strip()
            if not form:
                raise ValueError(f"provisional variant has no form for {entity.get('id')}")
            result.append((str(entity["id"]), form, str(entity.get("preferred_label") or "")))
            if canonicalize(form) not in aliases:
                raise ValueError(f"provisional variant is not an alias: {entity.get('id')} {form!r}")
    keys = [(entity_id, canonicalize(form)) for entity_id, form, _ in result]
    if len(keys) != len(set(keys)):
        raise ValueError("provisional spelling variants contain duplicate entity/form pairs")
    return result


def removed_aliases(base: dict[str, Any], target: dict[str, Any]) -> list[tuple[str, str, str]]:
    target_by_id = {str(row.get("id")): row for row in target.get("entities") or []}
    result = []
    for entity in base.get("entities") or []:
        entity_id = str(entity.get("id") or "")
        target_entity = target_by_id.get(entity_id) or {}
        target_aliases = set(target_entity.get("aliases") or [])
        for alias in entity.get("aliases") or []:
            if alias not in target_aliases:
                result.append((entity_id, str(alias), str(entity.get("preferred_label") or "")))
    return result


def count_rows(
    index: dict[tuple[str, str], list[dict[str, Any]]], entity_id: str, form: str, canonicalize
) -> list[dict[str, Any]]:
    return index.get((entity_id, canonicalize(form)), [])


def main() -> int:
    args = parse_args()
    chunks = list(read_jsonl(args.chunks))
    base = load_json(args.base_ontology)
    target = load_json(args.target_ontology)
    provisional = load_json(args.provisional_ontology)
    base_mentions = mentions_for(chunks, base, args.corpus_revision)
    target_mentions = mentions_for(chunks, target, args.corpus_revision)
    provisional_mentions = mentions_for(chunks, provisional, args.corpus_revision)
    base_index, target_index, provisional_index = map(
        keyed_rows, (base_mentions, target_mentions, provisional_mentions)
    )
    base_norm, target_norm, provisional_norm = map(normalizer, (base, target, provisional))

    markers = marked_forms(target)
    variants = provisional_variants(provisional)
    removed = removed_aliases(base, target)
    if len(markers) != 18:
        raise ValueError(f"expected 18 marked forms, found {len(markers)}")
    if len(variants) != 11:
        raise ValueError(f"expected 11 provisional spelling variants, found {len(variants)}")

    lines = [
        "# Jyotiṣa ontology mention-count comparison",
        "",
        f"- Corpus revision: `{args.corpus_revision}`",
        f"- Release: `{args.release_id}`",
        f"- Chunk windows: {len(chunks):,}",
        f"- Extractor: `{target_mentions[0]['extractor']['version'] if target_mentions else 'starter-gazetteer-0.2.0'}`",
        f"- Chunk SHA-256: `{sha256_file(args.chunks)}`",
        f"- v0.3 SHA-256: `{sha256_file(args.base_ontology)}`",
        f"- v0.3.1 SHA-256: `{sha256_file(args.target_ontology)}`",
        f"- provisional ontology SHA-256: `{sha256_file(args.provisional_ontology)}`",
        "",
        "Counts are extractor mention rows for each exact entity/form on the identical chunk inventory. “Unflagged” means the form is not listed in the finite ambiguity-marker list; it is not contextual or scholarly verification. v0.3 has no ambiguity assessment field, so its matching rows are unassessed. Contextual synonyms are not aliases and are excluded.",
        "",
        "## Ambiguity-marked forms (v0.3 → v0.3.1)",
        "",
        "| Entity | Form | Before total | After total | Flagged | Unflagged | Unassessed | Delta |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for entity_id, form, label in sorted(markers, key=lambda row: (row[0], row[1])):
        before = count_rows(base_index, entity_id, form, base_norm)
        after = count_rows(target_index, entity_id, form, target_norm)
        total, flagged, unflagged, unassessed = assessment(after)
        lines.append(
            f"| {label} (`{entity_id}`) | {form} | {len(before)} | {total} | {flagged} | {unflagged} | {unassessed} | {total-len(before):+d} |"
        )

    lines.extend([
        "",
        "## Removed aliases (v0.3 → v0.3.1)",
        "",
        "| Entity | Removed form | Before total | After total | Delta |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for entity_id, form, label in sorted(removed, key=lambda row: (row[0], row[1])):
        before = count_rows(base_index, entity_id, form, base_norm)
        after = count_rows(target_index, entity_id, form, target_norm)
        lines.append(f"| {label} (`{entity_id}`) | {form} | {len(before)} | {len(after)} | {len(after)-len(before):+d} |")

    lines.extend([
        "",
        "## Provisional spelling variants (v0.3.1 → v0.4.0-partial)",
        "",
        "| Entity | Variant | Before total | Provisional total | Delta |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for entity_id, form, label in sorted(variants, key=lambda row: (row[0], row[1])):
        before = count_rows(target_index, entity_id, form, target_norm)
        after = count_rows(provisional_index, entity_id, form, provisional_norm)
        lines.append(f"| {label} (`{entity_id}`) | {form} | {len(before)} | {len(after)} | {len(after)-len(before):+d} |")

    lines.extend([
        "",
        "## Whole-corpus mention assessment",
        "",
        "| Ontology | Total | Flagged | Unflagged | Unassessed |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for label, mentions in (("v0.3", base_mentions), ("v0.3.1", target_mentions), ("v0.4.0-partial", provisional_mentions)):
        total, flagged, unflagged, unassessed = assessment(mentions)
        lines.append(f"| {label} | {total} | {flagged} | {unflagged} | {unassessed} |")
    lines.append("")

    report = "\n".join(lines)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
