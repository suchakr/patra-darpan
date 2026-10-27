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
import subprocess
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
    parser.add_argument("--base-mentions", type=Path, default=None, help="optional verified base entity-mentions JSONL")
    parser.add_argument("--target-mentions", type=Path, default=None, help="optional verified target entity-mentions JSONL")
    parser.add_argument("--previous-target-mentions", type=Path, default=None, help="optional earlier-target entity-mentions JSONL")
    parser.add_argument(
        "--base-ontology", type=Path, default=ROOT / "ontology" / "jyotisha-v0.3.json"
    )
    parser.add_argument(
        "--target-ontology", type=Path, default=ROOT / "ontology" / "jyotisha-v0.3.1.json"
    )
    parser.add_argument(
        "--previous-target-ontology",
        type=Path,
        default=None,
        help="optional earlier target snapshot used to report removed ambiguity markers",
    )
    parser.add_argument(
        "--previous-target-git-ref",
        default=None,
        help="optional git show ref:path for an earlier target snapshot",
    )
    parser.add_argument(
        "--provisional-ontology", type=Path, default=None,
        help="optional ontology for spelling-variant counts; defaults to the target ontology",
    )
    parser.add_argument(
        "--expected-provisional-variants", type=int, default=None,
        help="optional assertion for the number of provisional spelling variants",
    )
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


def mentions_from_artifact(path: Path, revision: str) -> list[dict[str, Any]]:
    rows = list(read_jsonl(path))
    if not rows:
        raise ValueError(f"mention artifact is empty: {path}")
    mismatched = sum(str(row.get("corpus_revision") or "") != revision for row in rows)
    if mismatched:
        raise ValueError(f"{mismatched} rows in {path} do not match corpus revision {revision}")
    return rows


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


def removed_marker_forms(
    previous: dict[str, Any], current: dict[str, Any]
) -> list[tuple[str, str, str]]:
    current_keys = {(entity_id, form) for entity_id, form, _ in marked_forms(current)}
    return [
        row
        for row in marked_forms(previous)
        if (row[0], row[1]) not in current_keys
    ]


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
    if args.previous_target_ontology and args.previous_target_git_ref:
        raise ValueError("choose either --previous-target-ontology or --previous-target-git-ref")
    chunks = list(read_jsonl(args.chunks))
    base = load_json(args.base_ontology)
    target = load_json(args.target_ontology)
    previous_target_bytes = None
    if args.previous_target_git_ref:
        previous_target_bytes = subprocess.run(
            ["git", "-C", str(ROOT), "show", args.previous_target_git_ref],
            check=True,
            capture_output=True,
        ).stdout
        previous_target = json.loads(previous_target_bytes.decode("utf-8"))
        if not isinstance(previous_target, dict):
            raise ValueError("previous target git ref must contain a JSON object")
    elif args.previous_target_ontology:
        previous_target = load_json(args.previous_target_ontology)
        previous_target_bytes = args.previous_target_ontology.read_bytes()
    else:
        previous_target = None
    provisional = load_json(args.provisional_ontology) if args.provisional_ontology else target
    base_mentions = (
        mentions_from_artifact(args.base_mentions, args.corpus_revision)
        if args.base_mentions else mentions_for(chunks, base, args.corpus_revision)
    )
    target_mentions = (
        mentions_from_artifact(args.target_mentions, args.corpus_revision)
        if args.target_mentions else mentions_for(chunks, target, args.corpus_revision)
    )
    provisional_mentions = target_mentions if provisional is target else mentions_for(
        chunks, provisional, args.corpus_revision
    )
    previous_target_mentions = (
        mentions_from_artifact(args.previous_target_mentions, args.corpus_revision)
        if args.previous_target_mentions and previous_target is not None
        else mentions_for(chunks, previous_target, args.corpus_revision)
        if previous_target is not None
        else None
    )
    base_index, target_index, provisional_index = map(
        keyed_rows, (base_mentions, target_mentions, provisional_mentions)
    )
    base_norm, target_norm, provisional_norm = map(normalizer, (base, target, provisional))
    base_label = str(base.get("version") or "base")
    target_label = str(target.get("version") or "target")
    provisional_label = str(provisional.get("version") or "variant-source")

    markers = marked_forms(target)
    removed_markers = (
        removed_marker_forms(previous_target, target)
        if previous_target is not None
        else []
    )
    variants = provisional_variants(provisional)
    removed = removed_aliases(base, target)
    if not markers:
        raise ValueError("target ontology has no ambiguity-marked forms")
    if args.expected_provisional_variants is not None and len(variants) != args.expected_provisional_variants:
        raise ValueError(
            f"expected {args.expected_provisional_variants} provisional spelling variants, found {len(variants)}"
        )
    variant_baseline = previous_target if previous_target is not None else target
    if previous_target is None:
        variant_baseline_index = target_index
        variant_baseline_norm = target_norm
    else:
        variant_baseline_index = keyed_rows(previous_target_mentions or [])
        variant_baseline_norm = normalizer(previous_target)
    contextual_synonym_count = sum(
        entry.get("status") == "provisional"
        for entity in target.get("entities") or []
        for entry in ((entity.get("attributes") or {}).get("contextual_synonyms") or [])
        if isinstance(entry, dict)
    )
    target_annotations = [
        entry
        for entity in target.get("entities") or []
        for field in ("contextual_synonyms", "variant_evidence")
        for entry in ((entity.get("attributes") or {}).get(field) or [])
        if isinstance(entry, dict)
    ]
    target_status_counts = {
        status: sum(entry.get("status") == status for entry in target_annotations)
        for status in ("provisional", "approved")
    }
    variant_deltas = [
        len(count_rows(provisional_index, entity_id, form, provisional_norm))
        - len(count_rows(variant_baseline_index, entity_id, form, variant_baseline_norm))
        for entity_id, form, _ in variants
    ]

    lines = [
        "# Jyotiṣa ontology mention-count comparison",
        "",
        f"- Corpus revision: `{args.corpus_revision}`",
        f"- Release: `{args.release_id}`",
        f"- Chunk windows: {len(chunks):,}",
        f"- Extractor: `{target_mentions[0]['extractor']['version'] if target_mentions else 'starter-gazetteer-0.2.0'}`",
        f"- Chunk SHA-256: `{sha256_file(args.chunks)}`",
        *( [f"- Base mention artifact SHA-256: `{sha256_file(args.base_mentions)}`"] if args.base_mentions else [] ),
        *( [f"- Target mention artifact SHA-256: `{sha256_file(args.target_mentions)}`"] if args.target_mentions else [] ),
        *( [f"- Previous-target mention artifact SHA-256: `{sha256_file(args.previous_target_mentions)}`"] if args.previous_target_mentions else [] ),
        f"- Base ontology (v{base_label}) SHA-256: `{sha256_file(args.base_ontology)}`",
        f"- Target ontology (v{target_label}) SHA-256: `{sha256_file(args.target_ontology)}`",
        *(
            [f"- Previous target SHA-256: `{hashlib.sha256(previous_target_bytes).hexdigest()}`"]
            if previous_target_bytes is not None
            else []
        ),
        f"- Variant-source ontology (v{provisional_label}) SHA-256: `{sha256_file(args.provisional_ontology) if args.provisional_ontology else sha256_file(args.target_ontology)}`",
        f"- Target status-bearing annotations: {target_status_counts['provisional']} provisional, {target_status_counts['approved']} approved",
        "",
        f"Counts are extractor mention rows for each exact entity/form on the identical chunk inventory. “Unflagged” means the form is not listed in the finite ambiguity-marker list; it is not contextual or scholarly verification. The target contains {contextual_synonym_count} provisional contextual synonyms; these are metadata, not aliases. The {len(variants)} provisional spelling variants add {sum(variant_deltas):+d} matching mention rows against the stated baseline.",
        "",
        f"## Ambiguity-marked forms (v{base_label} → v{target_label})",
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

    if previous_target is not None and removed_markers:
        lines.extend([
            "",
            f"## Removed ambiguity markers (v{previous_target.get('version') or 'previous'} → v{target_label})",
            "",
            "Marker status is a disclosure label and does not affect matching. Counts remain stable where the aliases are unchanged.",
            "",
            "| Entity | Form | Previous flagged | Current total | Current flagged | Current unflagged | Current unassessed |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ])
        for entity_id, form, label in sorted(removed_markers, key=lambda row: (row[0], row[1])):
            before = count_rows(base_index, entity_id, form, base_norm)
            after = count_rows(target_index, entity_id, form, target_norm)
            _, flagged, unflagged, unassessed = assessment(after)
            lines.append(
                f"| {label} (`{entity_id}`) | {form} | {len(before)} | {len(after)} | {flagged} | {unflagged} | {unassessed} |"
            )

    lines.extend([
        "",
        f"## Removed aliases (v{base_label} → v{target_label})",
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
        f"## Provisional spelling variants (v{variant_baseline.get('version') or 'baseline'} → v{provisional_label})",
        "",
        "| Entity | Variant | Before total | After total | Delta |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for entity_id, form, label in sorted(variants, key=lambda row: (row[0], row[1])):
        before = count_rows(variant_baseline_index, entity_id, form, variant_baseline_norm)
        after = count_rows(provisional_index, entity_id, form, provisional_norm)
        lines.append(f"| {label} (`{entity_id}`) | {form} | {len(before)} | {len(after)} | {len(after)-len(before):+d} |")

    lines.extend([
        "",
        "## Whole-corpus mention assessment",
        "",
        "| Ontology | Total | Flagged | Unflagged | Unassessed |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    assessment_rows = [(f"v{base_label}", base_mentions)]
    if previous_target is not None and str(previous_target.get("version")) not in {base_label, target_label}:
        assessment_rows.append((
            f"v{previous_target.get('version')}",
            previous_target_mentions or [],
        ))
    assessment_rows.extend([
        (f"v{target_label}", target_mentions),
        (f"v{provisional_label}", provisional_mentions),
    ])
    seen_assessment_labels: set[str] = set()
    for label, mentions in assessment_rows:
        if label in seen_assessment_labels:
            continue
        seen_assessment_labels.add(label)
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
