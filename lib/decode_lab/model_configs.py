"""Model configurations for Gemini-based PDF extraction.

Three presets covering different cost/quality tradeoffs:

- ``flash-lite``  — cheapest, no thinking (~$5.65/corpus)
- ``flash``       — balanced, medium thinking
- ``3-flash``     — best quality, high thinking (~$43/corpus)

All presets share the same extraction prompt (derived from AI Studio
experimentation on 1.pdf and AKBag.pdf).  The only differences are
the API model name, thinking level, and page chunk size.

Usage::

    from lib.decode_lab.model_configs import get_model_config
    cfg = get_model_config("flash")
    # cfg.model_name, cfg.thinking_level, cfg.chunk_size, cfg.prompt
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# The universal extraction prompt (from AI Studio session)
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT_TEMPLATE = """\
**Role:** You are a high-fidelity academic transcription engine \
specialising in Indology and the History of Science.

**Scope:** Convert ONLY pages {start}–{end} of the attached PDF.
Do not summarise or skip any content within this range.
If you approach your output limit, complete the current paragraph \
or table row and insert the marker <<<CONTINUE>>> then stop.
Do not attempt to continue beyond that marker.

**Script & Symbol Fidelity:**
- IAST diacritics: output exact UTF-8 Unicode (ā ī ū ṛ ḷ ṅ ñ ṭ \
  ḍ ṇ ś ṣ ḥ ṃ). Do not substitute visually similar characters.
- Devanagari: transcribe in original script, do not romanise.
- Greek astronomical symbols: preserve exactly (α β γ δ ε ζ η λ).
- Mathematics: use LaTeX ($...$ inline, $$...$$ display).

**Structure:**
- # for paper title, ## for numbered sections, ### for subsections
- Tables: pipe syntax with ALL header rows including sub-header \
  rows (e.g. a "Star Count" group header with VGJ|PT|AVP|SKA|SCP \
  sub-columns must appear as two separate header rows)
- Footnotes: [^n] inline, definitions at end of page range
- Figures: for each figure or diagram, output:
  ![caption](figure-N-placeholder)
  <!-- figure-meta: page=N, position=top|middle|bottom, type=graph|diagram|photograph -->
  Use the actual page number from the PDF. Do not skip figures.

**Ambiguity rule:** If a character is unclear due to scan quality, \
use Indological context for best reading or mark [?].
Ignore scan noise (dust, edges) but capture every printed character.

**Output:** Markdown only. No commentary. No preamble. \
Start directly with the first heading or paragraph of page {start}."""


# ---------------------------------------------------------------------------
# Model config dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelConfig:
    """Configuration for one Gemini model variant."""

    name: str
    model_name: str
    thinking_level: str | None  # None, "LOW", "MEDIUM", "HIGH"
    chunk_size: int  # pages per Gemini call
    prompt_template: str = EXTRACTION_PROMPT_TEMPLATE

    def prompt_for_pages(self, start: int, end: int) -> str:
        """Return the prompt with page range filled in."""
        return self.prompt_template.format(start=start, end=end)

    def prompt_sha256(self, start: int, end: int) -> str:
        """SHA-256 of the rendered prompt (for provenance)."""
        return hashlib.sha256(
            self.prompt_for_pages(start, end).encode("utf-8")
        ).hexdigest()


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

_CONFIGS: dict[str, ModelConfig] = {
    "flash-lite": ModelConfig(
        name="flash-lite",
        model_name="gemini-2.5-flash-lite",
        thinking_level=None,
        chunk_size=5,
    ),
    "flash": ModelConfig(
        name="flash",
        model_name="gemini-2.5-flash",
        thinking_level=None,  # 2.5-flash uses built-in thinking, no explicit level
        chunk_size=5,
    ),
    "3-flash": ModelConfig(
        name="3-flash",
        model_name="gemini-3-flash-preview",
        thinking_level="HIGH",
        chunk_size=5,
    ),
    "3-flash-med": ModelConfig(
        name="3-flash-med",
        model_name="gemini-3-flash-preview",
        thinking_level="MEDIUM",
        chunk_size=5,
    ),
}

AVAILABLE_CONFIGS = list(_CONFIGS.keys())


def get_model_config(name: str) -> ModelConfig:
    """Return a ModelConfig by preset name.

    Raises ValueError if *name* is not a known preset.
    """
    if name not in _CONFIGS:
        raise ValueError(
            f"Unknown model config '{name}'. "
            f"Available: {', '.join(AVAILABLE_CONFIGS)}"
        )
    return _CONFIGS[name]
