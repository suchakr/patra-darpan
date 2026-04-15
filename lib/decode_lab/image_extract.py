"""Image extraction for the Darpan Decode Lab.

Extracts figures from PDFs using ``pdfimages -j``, filters out
watermarks/stencils, and caches results in ``.cache/images/<doc_id>/``.

For native PDFs: extracts embedded JPEG/PNG figures, names them
``p<page>_fig<N>.<ext>``.

For scanned PDFs: renders pages to PNG via ``pdftoppm`` and names
them ``p<page>_page.png``.

The cache is content-addressed by PDF SHA-256.  Re-extraction is
skipped if the PDF hasn't changed.

Usage::

    from lib.decode_lab.image_extract import extract_images
    images = extract_images(
        pdf_path=Path("corpus/ijhs/1.pdf"),
        doc_id="1",
        pdf_sha256="143af4c7...",
        images_jsonl=images_list,  # from pdfimages -list
    )
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from lib.config import PROJECT_ROOT


_CACHE_ROOT = PROJECT_ROOT / ".cache" / "images"

# Extensions that pdfimages -j produces for real images (not stencils)
_REAL_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".jp2"}


def extract_images(
    *,
    pdf_path: Path,
    doc_id: str,
    pdf_sha256: str,
    images_jsonl: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract figures from a PDF and cache them.

    Returns an updated image inventory with ``cached_path`` set for
    each extracted image.

    Skips extraction if the cache already has images for this doc_id
    with a matching PDF SHA-256.
    """
    cache_dir = _CACHE_ROOT / doc_id
    manifest_path = cache_dir / "_manifest.json"

    # Check if already cached for this PDF content
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("pdf_sha256") == pdf_sha256:
                return _load_cached_inventory(cache_dir, images_jsonl)
        except (json.JSONDecodeError, KeyError):
            pass

    # Fresh extraction
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Clean previous cache for this doc
    for old in cache_dir.glob("p*"):
        old.unlink()

    if not shutil.which("pdfimages"):
        return images_jsonl

    # Build page→image_num mapping from the inventory
    page_image_map = _build_page_image_map(images_jsonl)

    # Determine if this is a scanned PDF (every page is a full-page image)
    is_scanned = _is_scanned_pdf(images_jsonl)

    if is_scanned:
        _extract_scanned_pages(pdf_path, doc_id, cache_dir, images_jsonl)
    else:
        _extract_native_figures(pdf_path, doc_id, cache_dir, images_jsonl, page_image_map)

    # Write manifest
    manifest_path.write_text(
        json.dumps({"doc_id": doc_id, "pdf_sha256": pdf_sha256}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return _load_cached_inventory(cache_dir, images_jsonl)


def ensure_image_symlink(doc_dir: Path, doc_id: str) -> Path | None:
    """Create by-doc/<doc_id>/images/ symlink to the image cache.

    Returns the symlink path, or None if cache doesn't exist.
    """
    cache_dir = _CACHE_ROOT / doc_id
    if not cache_dir.exists():
        return None
    link_path = doc_dir / "images"
    if link_path.exists() or link_path.is_symlink():
        link_path.unlink()
    link_path.symlink_to(cache_dir)
    return link_path


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _is_scanned_pdf(images_jsonl: list[dict[str, Any]]) -> bool:
    """Heuristic: PDF is scanned if every page has exactly one large image."""
    if not images_jsonl:
        return False
    pages = set()
    large_count = 0
    for img in images_jsonl:
        pages.add(img.get("page_number"))
        w = img.get("width") or 0
        h = img.get("height") or 0
        if w > 1000 and h > 1000:
            large_count += 1
    # If large images == number of pages, it's scanned
    return large_count == len(pages) and large_count == len(images_jsonl)


def _build_page_image_map(
    images_jsonl: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    """Group images by page number, preserving order."""
    by_page: dict[int, list[dict[str, Any]]] = {}
    for img in images_jsonl:
        page = img.get("page_number", 0)
        by_page.setdefault(page, []).append(img)
    return by_page


def _extract_native_figures(
    pdf_path: Path,
    doc_id: str,
    cache_dir: Path,
    images_jsonl: list[dict[str, Any]],
    page_image_map: dict[int, list[dict[str, Any]]],
) -> None:
    """Extract real figures from a native PDF, skipping stencils."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        prefix = Path(tmpdir) / "img"
        subprocess.run(
            ["pdfimages", "-j", str(pdf_path), str(prefix)],
            capture_output=True,
            check=False,
        )

        # Map extracted files back to pages using the -list ordering
        extracted_files = sorted(Path(tmpdir).glob("img-*"))
        img_index = 0
        for img_meta in images_jsonl:
            if img_index >= len(extracted_files):
                break
            ext_file = extracted_files[img_index]
            img_index += 1

            # Skip stencils/watermarks (PBM files from pdfimages -j)
            if ext_file.suffix.lower() not in _REAL_IMAGE_EXTENSIONS:
                continue

            page = img_meta.get("page_number", 0)
            # Count which figure this is on this page
            page_imgs = page_image_map.get(page, [])
            real_imgs_on_page = [
                i for i in page_imgs
                if (i.get("width") or 0) > 500 or (i.get("height") or 0) > 500
            ]
            fig_idx = 1
            for ri in real_imgs_on_page:
                if ri.get("image_id") == img_meta.get("image_id"):
                    break
                fig_idx += 1

            dest_name = f"p{page:02d}_fig{fig_idx:02d}{ext_file.suffix.lower()}"
            dest_path = cache_dir / dest_name
            shutil.copy2(ext_file, dest_path)


def _extract_scanned_pages(
    pdf_path: Path,
    doc_id: str,
    cache_dir: Path,
    images_jsonl: list[dict[str, Any]],
) -> None:
    """For scanned PDFs, render each page to PNG."""
    if not shutil.which("pdftoppm"):
        return

    pages = sorted({img.get("page_number", 0) for img in images_jsonl})
    for page in pages:
        if page < 1:
            continue
        prefix = cache_dir / f"p{page:02d}_page"
        subprocess.run(
            [
                "pdftoppm",
                "-f", str(page),
                "-l", str(page),
                "-r", "150",  # lower DPI for display, not OCR
                "-png",
                str(pdf_path),
                str(prefix),
            ],
            capture_output=True,
            check=False,
        )
        # pdftoppm appends -NN to the prefix
        candidates = sorted(cache_dir.glob(f"p{page:02d}_page-*.png"))
        if candidates:
            # Rename to clean name
            candidates[0].rename(cache_dir / f"p{page:02d}_page.png")


def _load_cached_inventory(
    cache_dir: Path,
    images_jsonl: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the image inventory with cached_path filled in."""
    cached_files = {f.name: f for f in cache_dir.iterdir() if not f.name.startswith("_")}

    updated = []
    for img in images_jsonl:
        img = dict(img)  # copy
        page = img.get("page_number", 0)
        # Try to find a matching cached file for this page
        for name, path in cached_files.items():
            if name.startswith(f"p{page:02d}_"):
                img["cached_path"] = str(path)
                img["cached_name"] = name
                break
        updated.append(img)
    return updated


def replace_figure_placeholders(text: str, doc_id: str) -> str:
    """Replace figure-N-placeholder with actual image paths.

    Matches ``(figure-N-placeholder)`` in Markdown image syntax and
    replaces with ``(images/p<page>_fig<N>.jpg)`` based on the
    figure-meta annotation that follows.
    """
    cache_dir = _CACHE_ROOT / doc_id
    if not cache_dir.exists():
        return text

    cached_files = sorted(f.name for f in cache_dir.iterdir() if not f.name.startswith("_"))
    if not cached_files:
        return text

    # Build page→files index
    page_files: dict[int, list[str]] = {}
    for name in cached_files:
        m = re.match(r"p(\d+)_", name)
        if m:
            page = int(m.group(1))
            page_files.setdefault(page, []).append(name)

    lines = text.splitlines()
    result = []
    for i, line in enumerate(lines):
        if "figure-" in line and "-placeholder" in line:
            # Look for figure-meta in the next few lines to get page number
            page_num = _find_page_from_meta(lines, i)
            if page_num and page_num in page_files:
                files = page_files[page_num]
                # Use the first available file for this page
                replacement = f"images/{files[0]}"
                line = re.sub(
                    r"figure-\d+-placeholder",
                    replacement,
                    line,
                )
        result.append(line)
    return "\n".join(result)


def _find_page_from_meta(lines: list[str], img_line: int) -> int | None:
    """Search nearby lines for <!-- figure-meta: page=N ... -->."""
    for j in range(img_line, min(len(lines), img_line + 3)):
        m = re.search(r"page=(\d+)", lines[j])
        if m:
            return int(m.group(1))
    return None
