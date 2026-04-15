"""Gemini fallback for the Darpan Decode Lab.

Two fallback modes:

1. **Table crop fallback** — renders a page, crops the table bounding box,
   sends the crop to Gemini with a correction+extraction prompt, and applies
   the deterministic nakṣatra lookup.

2. **Full-page fallback** — renders a full page to PNG and sends it to Gemini
   with a prose extraction prompt.  For raster/scanned pages with zero text
   layer (`low_text_density` risk).  Also applies nakṣatra lookup.

Each step is recorded as a separate row in fallbacks.jsonl with full
SHA-256 provenance chain.  All Gemini calls are disk-cached.

Usage::

    from lib.decode_lab.gemini_fallback import (
        run_gemini_table_fallback,
        run_gemini_page_fallback,
    )
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from lib.config import PROJECT_ROOT
from lib.decode_lab.nakshatra_lookup import apply_nakshatra_corrections


# ---------------------------------------------------------------------------
# Disk cache for Gemini responses
# ---------------------------------------------------------------------------

_CACHE_DIR = PROJECT_ROOT / ".cache" / "gemini"


def _cache_key(prompt: str, image_bytes: bytes) -> str:
    """Compute a deterministic cache key from prompt + image content."""
    h = hashlib.sha256()
    h.update(prompt.encode("utf-8"))
    h.update(image_bytes)
    return h.hexdigest()


def _cache_get(key: str) -> str | None:
    """Return cached Gemini response text, or None on miss."""
    path = _CACHE_DIR / f"{key[:16]}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("cache_key") == key:
            return data["response_text"]
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _cache_put(key: str, response_text: str) -> None:
    """Store a Gemini response in the disk cache."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / f"{key[:16]}.json"
    path.write_text(
        json.dumps(
            {"cache_key": key, "response_text": response_text},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_CORRECTION_CONTEXT = """\
You are extracting a table from an academic paper on Indian astronomy.
While reading the image, watch for these systematic OCR-like confusions
in the source PDF rendering and correct them as you extract:

GREEK LETTERS — in star designations and catalogue references:
  The symbol that looks like German Eszett (ẞ) is actually Greek beta (β)
  The digit 8 in star designation columns is actually Greek delta (δ)
  Latin y in star designation columns is actually Greek gamma (γ)
  Latin a followed by a constellation abbreviation (Tau, Gem, Leo, Vir,
  Sco, Sgr, Ari, Psc, Aql, Ori, Boo, Crv, Lib, Aqr, Cnc, Hya, Del,
  PsA, Peg) is actually Greek alpha (α)

IAST DIACRITICS — in Sanskrit/IAST nakṣatra names and terms:
  Characters with cedilla (ş ș ţ ț) should have underdot instead (ṣ ṭ)
  Watch for underdotted consonants: ṛ ṇ ṣ ṭ ḍ ḥ — preserve them exactly

CONSTRAINTS:
- Only correct the specific confusions above
- Do not infer text you cannot see
- Do not reformat or summarise"""

_EXTRACTION_TASK = """\
Extract the full table as plain text with pipe (|) column separation.
Do NOT use markdown table syntax (no |---| separator lines).
Preserve all header rows exactly as they appear, including sub-header
rows that label column groups. Do not merge or collapse multi-row headers.
The table contains nakṣatra names, Sanskrit terms in IAST transliteration
(with diacritics like ā ī ū ṛ ṭ ṣ ṇ ḍ), Greek letters (α β γ δ ε ζ η λ),
and numerical values. Preserve all diacritics and special characters exactly.
Return the extracted table only, no commentary."""

COMBINED_PROMPT = _CORRECTION_CONTEXT + "\n\n" + _EXTRACTION_TASK

PROMPT_SHA256 = hashlib.sha256(COMBINED_PROMPT.encode("utf-8")).hexdigest()

# --- Full-page prose extraction prompt (for raster/scanned pages) ---

_PAGE_EXTRACTION_PROMPT = """\
You are extracting text from a scanned page of an academic paper on
Indian history of science and astronomy.

Extract ALL text visible on the page as plain text, preserving:
- Paragraph structure (use blank lines between paragraphs)
- Section headings
- Footnotes and references (place at the end of the page text)
- Mathematical expressions and equations (use Unicode where possible)
- Sanskrit and Hindi terms in IAST transliteration with diacritics
  (ā ī ū ṛ ṇ ṣ ṭ ḍ ḥ ś ṃ)
- Greek letters (α β γ δ ε ζ η θ λ μ ν π σ φ ω)
- Superscripts and subscripts (use Unicode or notation like x^2, H_2O)
- Table content if present (use pipe | separation)

CONSTRAINTS:
- Extract exactly what you see — do not summarise or interpret
- Do not add commentary or descriptions
- If a word is illegible, write [illegible] rather than guessing
- Preserve the reading order: title, authors, body, footnotes

Return the extracted text only."""

PAGE_PROMPT_SHA256 = hashlib.sha256(
    _PAGE_EXTRACTION_PROMPT.encode("utf-8")
).hexdigest()

# DPI for page rendering.
RENDER_DPI = 300
_PDF_POINTS_TO_PIXELS = RENDER_DPI / 72.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_page_to_png(
    pdf_path: Path, page_number: int, out_dir: Path
) -> Path | None:
    """Render a single PDF page to PNG at RENDER_DPI using pdftoppm.

    Returns the path to the rendered PNG, or None if pdftoppm is missing.
    """
    if not shutil.which("pdftoppm"):
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / f"page_{page_number:04d}"
    subprocess.run(
        [
            "pdftoppm",
            "-f", str(page_number),
            "-l", str(page_number),
            "-r", str(RENDER_DPI),
            "-png",
            str(pdf_path),
            str(prefix),
        ],
        capture_output=True,
        check=False,
    )
    # pdftoppm appends -NN to the prefix.
    candidates = sorted(out_dir.glob(f"page_{page_number:04d}-*.png"))
    return candidates[0] if candidates else None


def crop_png(
    png_path: Path,
    bbox: list[float],
    out_path: Path,
) -> Path | None:
    """Crop a PNG to a bounding box given in PDF points.

    Uses ImageMagick ``magick`` (preferred) or ``convert`` (deprecated).
    Returns the output path, or None if ImageMagick is unavailable.
    """
    magick = shutil.which("magick") or shutil.which("convert")
    if not magick:
        return None
    left = int(bbox[0] * _PDF_POINTS_TO_PIXELS)
    top = int(bbox[1] * _PDF_POINTS_TO_PIXELS)
    right = int(bbox[2] * _PDF_POINTS_TO_PIXELS)
    bottom = int(bbox[3] * _PDF_POINTS_TO_PIXELS)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            magick,
            str(png_path),
            "-crop", f"{width}x{height}+{left}+{top}",
            "+repage",
            str(out_path),
        ],
        capture_output=True,
        check=False,
    )
    return out_path if out_path.exists() else None


def call_gemini(
    image_bytes: bytes,
    prompt: str,
    *,
    model: str = "gemini-2.0-flash",
) -> str:
    """Send an image + prompt to Gemini and return the response text.

    Uses a disk cache keyed on SHA-256(prompt + image bytes).  A cache hit
    returns the saved response without an API call.  Requires GEMINI_API_KEY
    in the environment for cache misses.
    """
    key = _cache_key(prompt, image_bytes)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    from google import genai  # deferred import — only needed on cache miss

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set.  Export it or add to .env before running "
            "with --fallback gemini."
        )
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=[
            genai.types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            prompt,
        ],
    )
    text = response.text
    _cache_put(key, text)
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_gemini_table_fallback(
    *,
    pdf_path: Path,
    page_number: int,
    bbox: list[float],
    table_id: str,
    doc_id: str,
    work_dir: Path,
) -> list[dict[str, Any]]:
    """Run the two-step Gemini+lookup fallback for one table crop.

    Returns a list of two fallback records (Gemini call + lookup step)
    ready to be appended to fallbacks.jsonl.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    safe_tid = table_id.replace(":", "-")

    # --- Step 1: render page ---
    page_png = render_page_to_png(pdf_path, page_number, work_dir)
    if page_png is None:
        return [_error_record(table_id, doc_id, page_number, bbox, "pdftoppm not available")]

    # --- Step 2: crop ---
    crop_path = work_dir / f"{safe_tid}_crop.png"
    cropped = crop_png(page_png, bbox, crop_path)
    if cropped is None:
        return [_error_record(table_id, doc_id, page_number, bbox, "crop failed (ImageMagick)")]

    crop_bytes = crop_path.read_bytes()
    crop_sha = _sha256_bytes(crop_bytes)

    # --- Step 3: Gemini call ---
    try:
        gemini_text = call_gemini(crop_bytes, COMBINED_PROMPT)
    except Exception as exc:
        return [_error_record(table_id, doc_id, page_number, bbox, f"Gemini call failed: {exc}")]

    gemini_out_path = work_dir / f"{safe_tid}_gemini.txt"
    gemini_out_path.write_text(gemini_text, encoding="utf-8")
    gemini_sha = _sha256_text(gemini_text)

    gemini_record: dict[str, Any] = {
        "fallback_id": f"{safe_tid}-gemini-combined",
        "doc_id": doc_id,
        "page_number": page_number,
        "bbox": bbox,
        "fallback_type": "ocr_crop",
        "tool_or_model": "gemini-2.0-flash",
        "tool_or_model_version": "gemini-2.0-flash",
        "prompt_sha256": PROMPT_SHA256,
        "input_sha256": crop_sha,
        "output_sha256": gemini_sha,
        "status": "partial",
        "status_reason": "Gemini extraction with correction prompt; nakṣatra lookup pending.",
        "recommended_action": "nakshatra-lookup",
    }

    # --- Step 4: deterministic lookup ---
    cleaned_text = apply_nakshatra_corrections(gemini_text)
    cleaned_out_path = work_dir / f"{safe_tid}_cleaned.txt"
    cleaned_out_path.write_text(cleaned_text, encoding="utf-8")
    cleaned_sha = _sha256_text(cleaned_text)

    changed = gemini_sha != cleaned_sha

    lookup_record: dict[str, Any] = {
        "fallback_id": f"{safe_tid}-nakshatra-lookup",
        "doc_id": doc_id,
        "page_number": page_number,
        "bbox": bbox,
        "fallback_type": "deterministic_postprocess",
        "tool_or_model": "python-nakshatra-lookup",
        "tool_or_model_version": "v1",
        "prompt_sha256": None,
        "input_sha256": gemini_sha,
        "output_sha256": cleaned_sha,
        "status": "success",
        "status_reason": (
            f"Nakṣatra lookup applied ({'corrections made' if changed else 'no changes needed'})."
        ),
        "recommended_action": "accept",
    }

    return [gemini_record, lookup_record]


def run_gemini_page_fallback(
    *,
    pdf_path: Path,
    page_number: int,
    doc_id: str,
    work_dir: Path,
) -> list[dict[str, Any]]:
    """Run Gemini full-page extraction for a raster/scanned page.

    Renders the page to PNG, sends the full image to Gemini with a prose
    extraction prompt, then applies the nakṣatra lookup.
    Returns a list of fallback records ready for fallbacks.jsonl.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    page_tag = f"{doc_id}-p{page_number:04d}"

    # --- Step 1: render page ---
    page_png = render_page_to_png(pdf_path, page_number, work_dir)
    if page_png is None:
        return [_error_record_page(doc_id, page_number, "pdftoppm not available")]

    page_bytes = page_png.read_bytes()
    page_sha = _sha256_bytes(page_bytes)

    # --- Step 2: Gemini call ---
    try:
        gemini_text = call_gemini(page_bytes, _PAGE_EXTRACTION_PROMPT)
    except Exception as exc:
        return [_error_record_page(doc_id, page_number, f"Gemini call failed: {exc}")]

    gemini_out_path = work_dir / f"{page_tag}_gemini.txt"
    gemini_out_path.write_text(gemini_text, encoding="utf-8")
    gemini_sha = _sha256_text(gemini_text)

    gemini_record: dict[str, Any] = {
        "fallback_id": f"{page_tag}-gemini-page",
        "doc_id": doc_id,
        "page_number": page_number,
        "bbox": None,
        "fallback_type": "ocr_page",
        "tool_or_model": "gemini-2.0-flash",
        "tool_or_model_version": "gemini-2.0-flash",
        "prompt_sha256": PAGE_PROMPT_SHA256,
        "input_sha256": page_sha,
        "output_sha256": gemini_sha,
        "status": "partial",
        "status_reason": "Gemini full-page extraction; nakṣatra lookup pending.",
        "recommended_action": "nakshatra-lookup",
    }

    # --- Step 3: deterministic lookup ---
    cleaned_text = apply_nakshatra_corrections(gemini_text)
    cleaned_out_path = work_dir / f"{page_tag}_cleaned.txt"
    cleaned_out_path.write_text(cleaned_text, encoding="utf-8")
    cleaned_sha = _sha256_text(cleaned_text)

    changed = gemini_sha != cleaned_sha

    lookup_record: dict[str, Any] = {
        "fallback_id": f"{page_tag}-nakshatra-lookup",
        "doc_id": doc_id,
        "page_number": page_number,
        "bbox": None,
        "fallback_type": "deterministic_postprocess",
        "tool_or_model": "python-nakshatra-lookup",
        "tool_or_model_version": "v1",
        "prompt_sha256": None,
        "input_sha256": gemini_sha,
        "output_sha256": cleaned_sha,
        "status": "success",
        "status_reason": (
            f"Nakṣatra lookup applied ({'corrections made' if changed else 'no changes needed'})."
        ),
        "recommended_action": "accept",
    }

    return [gemini_record, lookup_record]


def _error_record(
    table_id: str, doc_id: str, page_number: int, bbox: list[float], reason: str
) -> dict[str, Any]:
    return {
        "fallback_id": f"{table_id.replace(':', '-')}-gemini-combined",
        "doc_id": doc_id,
        "page_number": page_number,
        "bbox": bbox,
        "fallback_type": "ocr_crop",
        "tool_or_model": "gemini-2.0-flash",
        "tool_or_model_version": "gemini-2.0-flash",
        "prompt_sha256": PROMPT_SHA256,
        "input_sha256": None,
        "output_sha256": None,
        "status": "failure",
        "status_reason": reason,
        "recommended_action": "no-action",
    }


def _error_record_page(
    doc_id: str, page_number: int, reason: str
) -> dict[str, Any]:
    return {
        "fallback_id": f"{doc_id}-p{page_number:04d}-gemini-page",
        "doc_id": doc_id,
        "page_number": page_number,
        "bbox": None,
        "fallback_type": "ocr_page",
        "tool_or_model": "gemini-2.0-flash",
        "tool_or_model_version": "gemini-2.0-flash",
        "prompt_sha256": PAGE_PROMPT_SHA256,
        "input_sha256": None,
        "output_sha256": None,
        "status": "failure",
        "status_reason": reason,
        "recommended_action": "no-action",
    }
