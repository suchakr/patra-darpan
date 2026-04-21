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
    text = _fix_malformed_image_links(text)
    text = _fix_latex_superscript_spacing(text)
    text = _add_visible_image_captions(text)
    text = _normalize_block_spacing(text)
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


def _fix_malformed_image_links(text: str) -> str:
    r"""Repair Gemini's occasional reversed image syntax.

    Pattern: ``!(caption)[media/p01.png]`` → ``![caption](media/p01.png)``
    """
    return re.sub(r"!\(([^)\n]+)\)\[([^\]\n]+)\]", r"![\1](\2)", text)


def _add_visible_image_captions(text: str) -> str:
    """Add a visible Markdown caption after image links with useful alt text.

    Markdown image alt text is accessibility text, not a visible caption.
    The decoded corpus needs the figure caption to render for human audit.
    """
    lines = text.splitlines()
    result: list[str] = []
    for index, line in enumerate(lines):
        result.append(line)
        match = re.match(r"^!\[([^\]]+)\]\(([^)]+)\)\s*$", line.strip())
        if not match:
            continue
        caption = match.group(1).strip()
        if not caption or caption.lower() in {"image", "figure"}:
            continue
        next_line = _next_non_empty_line(lines, index + 1)
        if _is_caption_line(next_line, caption):
            continue
        result.append(f"*{caption}*")
    return "\n".join(result)


def _normalize_block_spacing(text: str) -> str:
    """Add blank lines around Markdown blocks that often bleed in renderers.

    Gemini sometimes emits perfectly readable Markdown source that renders
    poorly because headings, tables, images, or display math are adjacent to
    prose. This keeps table rows together, but separates table blocks from
    surrounding text.
    """
    lines = _split_attached_table_lines(text.splitlines())
    if not lines:
        return text

    out: list[str] = []
    for index, line in enumerate(lines):
        previous_line = lines[index - 1] if index > 0 else ""
        next_line = lines[index + 1] if index + 1 < len(lines) else ""

        needs_blank_before = (
            _is_heading(line)
            or _is_image(line)
            or _is_html_comment(line)
            or _is_footnote_definition(line)
            or _starts_display_math(line)
            or (_is_table_line(line) and not _is_table_line(previous_line))
        )
        if needs_blank_before and out and out[-1].strip():
            out.append("")

        out.append(line)

        needs_blank_after = (
            _is_heading(line)
            or _is_image(line)
            or _is_html_comment(line)
            or _is_footnote_definition(line)
            or _ends_display_math(line)
            or (_is_table_line(line) and not _is_table_line(next_line))
        )
        if needs_blank_after and next_line.strip():
            out.append("")

    return _collapse_blank_lines("\n".join(out)).strip() + "\n"


def _is_heading(line: str) -> bool:
    return bool(re.match(r"^#{1,6}\s+\S", line.strip()))


def _is_image(line: str) -> bool:
    return line.strip().startswith("![")


def _is_caption_line(line: str, caption: str) -> bool:
    stripped = line.strip()
    return stripped in {caption, f"*{caption}*", f"_{caption}_"}


def _next_non_empty_line(lines: list[str], start: int) -> str:
    for line in lines[start:]:
        if line.strip():
            return line.strip()
    return ""


def _is_footnote_definition(line: str) -> bool:
    return bool(re.match(r"^\[\^[^\]]+\]:\s+", line.strip()))


def _is_html_comment(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("<!--") and stripped.endswith("-->")


def _starts_display_math(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("$$") or stripped.startswith(r"\[")


def _ends_display_math(line: str) -> bool:
    stripped = line.strip()
    return (
        (stripped.endswith("$$") and stripped != "$$")
        or stripped.endswith(r"\]")
    )


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|") or "|" not in stripped[1:]:
        return False
    return stripped.endswith("|")


def _split_attached_table_lines(lines: list[str]) -> list[str]:
    """Split prose glued to a Markdown table row onto separate lines.

    Pattern seen in audits:
    ``Some prose | Col A | Col B |`` followed by a table separator row.

    We only split when the pipe suffix is adjacent to another table row, which
    keeps ordinary prose containing vertical bars intact.
    """
    result: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if _is_table_line(stripped):
            result.append(line)
            continue

        match = re.match(r"^(.+?\S)\s+(\|.+\|)\s*$", line)
        if not match or not _is_table_line(match.group(2)):
            result.append(line)
            continue

        previous_line = lines[index - 1].strip() if index > 0 else ""
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if _is_table_line(previous_line) or _is_table_line(next_line):
            result.append(match.group(1))
            result.append(match.group(2))
        else:
            result.append(line)
    return result


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)
