"""Deterministic Patra Darpan -> Sanchaya retrieval exporter.

The exporter deliberately stops at a reviewed corpus projection. It does not
build Zoekt, vectors, entities, or MCP state. The latter stages consume the
Sanchaya commit produced here.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlparse


EXPORT_VERSION = "retrieval-export.v0.1"
DEFAULT_GCS_BUCKET = "cahcblr-pdfs"
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
PLACEHOLDER_RE = re.compile(r"(?:placeholder|figure-[^/]+-(?:top|middle|bottom))", re.I)
SKIP_MEDIA_NAMES = {"_manifest.json"}


@dataclass(frozen=True)
class ExportPlan:
    doc_id: str
    source_dir: Path
    destination_dir: Path
    manifest_row: dict[str, Any]
    warnings: tuple[str, ...]


@dataclass
class ExportResult:
    selected: list[str]
    exported: list[str]
    skipped: list[str]
    warnings: list[str]
    errors: list[str]
    manifest_rows: list[dict[str, Any]]
    applied: bool

    @property
    def ok(self) -> bool:
        return not self.errors


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_no}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected object at {path}:{line_no}")
            rows.append(value)
    return rows


def read_index_tsv(path: Path | None) -> dict[str, dict[str, str]]:
    """Index existing Patra Darpan metadata by gcs key and filename stem."""

    if path is None or not path.exists():
        return {}
    result: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            normalized = {str(k): str(v or "").strip() for k, v in row.items()}
            key = normalized.get("gcs_key", "")
            if not key:
                continue
            result.setdefault(key, normalized)
            stem = Path(key).stem
            if stem:
                result.setdefault(stem, normalized)
    return result


def validate_doc_id(doc_id: str) -> None:
    if not doc_id or doc_id in {".", ".."}:
        raise ValueError("document ID must be non-empty")
    if "/" in doc_id or "\\" in doc_id or Path(doc_id).name != doc_id:
        raise ValueError(f"document ID is not a safe single path component: {doc_id!r}")


def classify_source_kind(uri: str) -> str:
    host = (urlparse(uri).hostname or "").lower()
    if "insa.nic.in" in host:
        return "insa-ijhs"
    if "cahc.jainuniversity.ac.in" in host:
        return "cahc"
    if host == "storage.googleapis.com" or uri.startswith("gs://"):
        return "gcs"
    return "external"


def _add_source_ref(
    refs: list[dict[str, Any]],
    *,
    kind: str,
    role: str,
    uri: str,
    **extra: Any,
) -> None:
    uri = uri.strip()
    if not uri or any(ref.get("uri") == uri for ref in refs):
        return
    ref: dict[str, Any] = {"kind": kind, "role": role, "uri": uri}
    ref.update({key: value for key, value in extra.items() if value})
    refs.append(ref)


def build_source_refs(
    source: dict[str, Any], index_row: dict[str, str], *, gcs_bucket: str
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []

    primary_uri = str(source.get("source_url") or index_row.get("url") or "").strip()
    if primary_uri:
        kind = classify_source_kind(primary_uri)
        role = "primary_pdf" if str(index_row.get("entry_type") or "pdf") != "link" else "source_page"
        _add_source_ref(refs, kind=kind, role=role, uri=primary_uri)

    mirror_uri = str(source.get("ju_url") or index_row.get("ju_url") or "").strip()
    if mirror_uri:
        _add_source_ref(refs, kind=classify_source_kind(mirror_uri), role="mirror_pdf", uri=mirror_uri)

    explicit_gcs = str(source.get("gcs_uri") or index_row.get("gcs_uri") or "").strip()
    if explicit_gcs:
        _add_source_ref(refs, kind="gcs", role="managed_asset", uri=explicit_gcs)

    gcs_key = str(source.get("gcs_key") or index_row.get("gcs_key") or "").strip().lstrip("/")
    if gcs_key:
        gs_uri = f"gs://{gcs_bucket}/assets/{gcs_key}"
        https_uri = f"https://storage.googleapis.com/{gcs_bucket}/assets/{gcs_key}"
        _add_source_ref(
            refs,
            kind="gcs",
            role="managed_asset",
            uri=gs_uri,
            https_uri=https_uri,
        )
    return refs


def _year(value: Any) -> int | str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}", text):
        return int(text)
    return text


def _categories(index_row: dict[str, str]) -> tuple[str, list[str]]:
    values: list[str] = []
    for key in ("subject", "category"):
        value = str(index_row.get(key) or "").strip()
        if value and value not in values:
            values.append(value)
    return (values[0] if values else "unclassified", values)


def _quality_warnings(quality: dict[str, Any]) -> list[str]:
    warnings = quality.get("warnings") or []
    result: list[str] = []
    for warning in warnings:
        if isinstance(warning, dict):
            result.append(str(warning.get("type") or "warning"))
        else:
            result.append(str(warning))
    return result


def _relative_media_target(target: str) -> str:
    return target.split("#", 1)[0].split("?", 1)[0].strip()


def validate_media_links(markdown: str, source_dir: Path) -> tuple[list[str], list[str]]:
    """Return (warnings, errors) for local Markdown image references."""

    warnings: list[str] = []
    errors: list[str] = []
    for target in IMAGE_RE.findall(markdown):
        relative = _relative_media_target(target)
        if not relative or relative.startswith("//") or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", relative):
            continue
        if PLACEHOLDER_RE.search(relative):
            warnings.append(f"unresolved image placeholder: {relative}")
            continue
        candidate = (source_dir / relative).resolve()
        try:
            candidate.relative_to(source_dir.resolve())
        except ValueError:
            errors.append(f"image reference escapes document directory: {relative}")
            continue
        if not candidate.is_file():
            errors.append(f"missing local image: {relative}")
    return warnings, errors


def _copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        if item.name in SKIP_MEDIA_NAMES:
            continue
        target = destination / relative
        if item.is_symlink():
            raise ValueError(f"symlink is not allowed in exported media: {item}")
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _tree_hashes(root: Path, *, exported_paper: bool = False) -> dict[str, str]:
    result: dict[str, str] = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        if path.is_file():
            if exported_paper and (
                path.name in {"manifest.json", "quality.json", "_manifest.json"}
                or path.relative_to(root).parts[0] not in {"document.md", "media"}
            ):
                continue
            result[str(path.relative_to(root))] = sha256_file(path)
    return result


def _same_tree(left: Path, right: Path) -> bool:
    return _tree_hashes(left) == _tree_hashes(right)


def _same_exported_paper(left: Path, right: Path) -> bool:
    return _tree_hashes(left, exported_paper=True) == _tree_hashes(right, exported_paper=True)


def _source_row(
    *,
    decoded_root: Path,
    doc_id: str,
    per_doc_manifest: dict[str, Any],
    quality: dict[str, Any],
    index_row: dict[str, str],
    destination_root: Path,
    gcs_bucket: str,
) -> dict[str, Any]:
    source = per_doc_manifest.get("source") or {}
    primary_category, categories = _categories(index_row)
    title = str(source.get("title") or index_row.get("paper") or doc_id).strip()
    author = str(source.get("author_display") or index_row.get("author") or "").strip()
    markdown_path = decoded_root / "by-doc" / doc_id / "document.md"
    document_sha = sha256_file(markdown_path)
    repo_paper = PurePosixPath("patra-darpan", "papers", doc_id)
    row: dict[str, Any] = {
        "schema_version": "retrieval.corpus-manifest.v1",
        "document_id": f"pd:{doc_id}",
        "source_kind": "patra-darpan",
        "source_doc_id": doc_id,
        "repo_path": str(repo_paper / "document.md"),
        "title": title,
        "authors": [author] if author else [],
        "year": _year(source.get("year") or index_row.get("year")),
        "journal": str(source.get("journal_label") or index_row.get("journal") or "").strip(),
        "primary_category": primary_category,
        "categories": categories,
        "content_sha256": document_sha,
        "source_refs": build_source_refs(source, index_row, gcs_bucket=gcs_bucket),
        "source_pdf_sha256": per_doc_manifest.get("source_pdf_sha256"),
        "media_prefix": str(repo_paper / "media") + "/",
        "quality_status": str(quality.get("status") or per_doc_manifest.get("status") or "unknown"),
        "quality_warnings": _quality_warnings(quality),
        "extractor_version": str(per_doc_manifest.get("extractor") or "").strip() or None,
        "extraction_run_id": str(per_doc_manifest.get("run_id") or "").strip() or None,
        "export_version": EXPORT_VERSION,
    }
    return {key: value for key, value in row.items() if value is not None}


def _load_decoded_rows(decoded_root: Path) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(decoded_root / "manifest.jsonl")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        doc_id = str(row.get("doc_id") or "").strip()
        if not doc_id:
            continue
        validate_doc_id(doc_id)
        if doc_id in result:
            raise ValueError(f"duplicate decoded document ID: {doc_id}")
        result[doc_id] = row
    return result


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def export_documents(
    *,
    decoded_root: Path,
    sanchaya_root: Path,
    doc_ids: list[str] | None = None,
    index_tsv: Path | None = None,
    gcs_bucket: str = DEFAULT_GCS_BUCKET,
    apply: bool = False,
    replace_existing: bool = False,
) -> ExportResult:
    """Plan or apply a deterministic export of selected decoded documents."""

    decoded_root = decoded_root.resolve()
    sanchaya_root = sanchaya_root.expanduser().resolve()
    decoded_rows = _load_decoded_rows(decoded_root)
    selected = list(doc_ids) if doc_ids else sorted(decoded_rows)
    errors: list[str] = []
    warnings: list[str] = []
    plans: list[ExportPlan] = []
    index_lookup = read_index_tsv(index_tsv.resolve() if index_tsv else None)

    for doc_id in selected:
        try:
            validate_doc_id(doc_id)
            if doc_id not in decoded_rows:
                raise ValueError("not present in decoded-corpus/manifest.jsonl")
            row = decoded_rows[doc_id]
            if str(row.get("status") or "ok") not in {"ok", "warning"}:
                raise ValueError(f"decoded status is {row.get('status')!r}")
            source_dir = decoded_root / "by-doc" / doc_id
            markdown_path = source_dir / "document.md"
            per_doc_manifest_path = source_dir / "manifest.json"
            quality_path = source_dir / "quality.json"
            for required in (markdown_path, per_doc_manifest_path, quality_path):
                if not required.is_file():
                    raise ValueError(f"missing required file: {required}")
            per_doc_manifest = read_json(per_doc_manifest_path)
            quality = read_json(quality_path)
            markdown = markdown_path.read_text(encoding="utf-8")
            link_warnings, link_errors = validate_media_links(markdown, source_dir)
            warnings.extend(f"{doc_id}: {message}" for message in link_warnings)
            if link_errors:
                raise ValueError("; ".join(link_errors))
            source = per_doc_manifest.get("source") or {}
            index_row = index_lookup.get(str(source.get("gcs_key") or "")) or index_lookup.get(doc_id, {})
            destination_dir = sanchaya_root / "patra-darpan" / "papers" / doc_id
            manifest_row = _source_row(
                decoded_root=decoded_root,
                doc_id=doc_id,
                per_doc_manifest=per_doc_manifest,
                quality=quality,
                index_row=index_row,
                destination_root=sanchaya_root,
                gcs_bucket=gcs_bucket,
            )
            plans.append(
                ExportPlan(
                    doc_id=doc_id,
                    source_dir=source_dir,
                    destination_dir=destination_dir,
                    manifest_row=manifest_row,
                    warnings=tuple(link_warnings),
                )
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{doc_id}: {exc}")

    if errors:
        return ExportResult(selected, [], [], warnings, errors, [], apply)

    exported: list[str] = []
    skipped: list[str] = []
    for plan in plans:
        if plan.destination_dir.exists():
            if _same_exported_paper(plan.source_dir, plan.destination_dir):
                skipped.append(plan.doc_id)
            elif not replace_existing:
                errors.append(
                    f"{plan.doc_id}: destination exists and differs; pass replace_existing=True to replace it"
                )

    if errors:
        return ExportResult(selected, [], skipped, warnings, errors, [], apply)

    catalog_path = sanchaya_root / "patra-darpan" / "catalog" / "corpus-manifest.jsonl"
    existing_rows = {str(row.get("document_id")): row for row in read_jsonl(catalog_path)}
    for plan in plans:
        existing_rows[plan.manifest_row["document_id"]] = plan.manifest_row
        if plan.doc_id not in skipped:
            exported.append(plan.doc_id)

    manifest_rows = [existing_rows[key] for key in sorted(existing_rows)]
    if apply:
        if not sanchaya_root.exists():
            raise FileNotFoundError(f"Sanchaya root does not exist: {sanchaya_root}")
        with tempfile.TemporaryDirectory(prefix="retrieval-export-", dir=str(sanchaya_root)) as temp_dir:
            staging_root = Path(temp_dir)
            staged_manifest = staging_root / "patra-darpan" / "catalog" / "corpus-manifest.jsonl"
            _write_jsonl(staged_manifest, manifest_rows)
            staged_docs: list[tuple[ExportPlan, Path]] = []
            for plan in plans:
                if plan.doc_id in skipped:
                    continue
                staged = staging_root / "patra-darpan" / "papers" / plan.doc_id
                staged.mkdir(parents=True, exist_ok=True)
                shutil.copy2(plan.source_dir / "document.md", staged / "document.md")
                media_source = plan.source_dir / "media"
                if media_source.is_dir():
                    _copy_tree(media_source, staged / "media")
                staged_docs.append((plan, staged))

            for plan, staged in staged_docs:
                destination = plan.destination_dir
                if destination.exists():
                    if not replace_existing:
                        raise FileExistsError(f"destination changed during export: {destination}")
                    shutil.rmtree(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(staged, destination)
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged_manifest, catalog_path)

    return ExportResult(selected, exported, skipped, warnings, [], manifest_rows, apply)


def write_audit(path: Path, result: ExportResult) -> None:
    payload = {
        "schema_version": "retrieval.export-audit.v1",
        "generated_at": utc_now(),
        "applied": result.applied,
        "selected": result.selected,
        "exported": result.exported,
        "skipped": result.skipped,
        "warnings": result.warnings,
        "errors": result.errors,
        "ok": result.ok,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
