"""Deterministic Markdown fixups for Gemini extraction output.

Small corrections that are cheaper and more reliable to apply as
post-processing than to engineer into the Gemini prompt.  Each fixup
is a simple regex or string replacement — no LLM, no inference.

Add new fixups here as patterns are discovered.  Each should be:
- Deterministic (same input → same output)
- Safe (no false positives on normal academic text)
- Documented with the pattern it corrects

Usage::

    from lib.decode_lab.markdown_fixups import apply_markdown_fixups
    cleaned = apply_markdown_fixups(gemini_text)
"""

from __future__ import annotations

import re


def apply_markdown_fixups(text: str) -> str:
    """Apply all registered fixups to *text*.  Returns corrected text."""
    text = _fix_latex_superscript_spacing(text)
    return text


def _fix_latex_superscript_spacing(text: str) -> str:
    r"""Pad a space before inline LaTeX superscripts glued to preceding word.

    Pattern: ``word$^{...}`` → ``word $^{...}``

    Gemini sometimes omits the space before footnote-style LaTeX
    superscripts like ``it$^{8,9,10}$`` or ``text$^1$``.
    """
    # Match: non-space char immediately followed by $^ (start of superscript)
    text = re.sub(r'(\S)(\$\^)', r'\1 \2', text)
    return text
