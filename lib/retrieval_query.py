"""Explicit script expansion for literal Sanskrit terms; raw Zoekt stays raw.

Based on Sanchaya Advanced Search's mappings, with explicit input schemes,
NFC normalization and terminal consonants handled conservatively. This is
transliteration, not morphology or synonym generation.
"""
from __future__ import annotations

import re
import unicodedata


VOWELS = "अ आ इ ई उ ऊ ऋ ॠ ऌ ॡ ए ऐ ओ औ".split()
MATRAS = ["", *"ा ि ी ु ू ृ ॄ ॢ ॣ े ै ो ौ".split()]
CONSONANTS = "क ख ग घ ङ च छ ज झ ञ ट ठ ड ढ ण त थ द ध न प फ ब भ म य र ल व श ष स ह ळ".split()
IAST_V = "a ā i ī u ū ṛ ṝ ḷ ḹ e ai o au".split()
HK_V = "a A i I u U R RR lR lRR e ai o au".split()
IAST_C = "k kh g gh ṅ c ch j jh ñ ṭ ṭh ḍ ḍh ṇ t th d dh n p ph b bh m y r l v ś ṣ s h ḻ".split()
HK_C = "k kh g gh G c ch j jh J T Th D Dh N t th d dh n p ph b bh m y r l v z S s h L".split()


def to_devanagari(term: str, scheme: str) -> str:
    # IAST capitalization is presentation; HK capitalization encodes phonemes.
    if scheme == "iast":
        term = term.casefold()
    vowels = dict(zip(IAST_V if scheme == "iast" else HK_V, zip(VOWELS, MATRAS)))
    consonants = dict(zip(IAST_C if scheme == "iast" else HK_C, CONSONANTS))
    signs = {"ṃ": "ं", "ṁ": "ं", "ḥ": "ः", "'": "ऽ"} if scheme == "iast" else {"M": "ं", "H": "ः", "'": "ऽ"}
    tokens = sorted(set(vowels) | set(consonants) | set(signs), key=len, reverse=True)
    out = ""
    pending = False
    i = 0
    while i < len(term):
        token = next((s for s in tokens if term.startswith(s, i)), None)
        if token is None:
            raise ValueError(f"cannot transliterate {term!r} as {scheme}; use raw search for mixed text")
        if token in consonants:
            if pending:
                out += "्"
            out += consonants[token]
            pending = True
        elif token in vowels:
            independent, matra = vowels[token]
            out += matra if pending else independent
            pending = False
        else:
            if pending and token == "'":
                out += "्"
            out += signs[token]
            pending = False
        i += len(token)
    if pending:
        out += "्"
    return out


def from_devanagari(term: str, scheme: str) -> str:
    vs = IAST_V if scheme == "iast" else HK_V
    cs = IAST_C if scheme == "iast" else HK_C
    vowels = dict(zip(VOWELS, vs))
    matras = dict(zip(MATRAS[1:], vs[1:]))
    consonants = dict(zip(CONSONANTS, cs))
    signs = {"ं": "ṃ", "ः": "ḥ", "ँ": "m̐", "ऽ": "'"} if scheme == "iast" else {"ं": "M", "ः": "H", "ँ": "M", "ऽ": "'"}
    out = ""
    pending = False
    for ch in term:
        if ch in consonants:
            if pending:
                out += "a"
            out += consonants[ch]
            pending = True
        elif ch in matras:
            if not pending:
                raise ValueError(f"unattached vowel mark in {term!r}")
            out += matras[ch]
            pending = False
        elif ch == "्":
            pending = False
        elif ch in vowels or ch in signs:
            if pending:
                out += "a"
            out += vowels.get(ch, signs.get(ch, ""))
            pending = False
        else:
            raise ValueError(f"unsupported character in {term!r}; use raw search")
    return out + ("a" if pending else "")


def prepare_lexical_query(query: str, *, script_expansion: str = "none", file_filter: str | None = None,
                          result_type: str = "matches") -> tuple[str, list[dict], list[str]]:
    """Expand only plain terms; never rewrite Zoekt operators or regex."""
    if len(query.encode("utf-8")) > 8192 or not query.strip():
        raise ValueError("query must be nonempty and at most 8192 UTF-8 bytes")
    if script_expansion not in {"none", "auto", "devanagari", "iast", "harvard_kyoto"}:
        raise ValueError("script_expansion must be none, auto, devanagari, iast, or harvard_kyoto")
    if result_type not in {"matches", "files"}:
        raise ValueError("result_type must be matches or files")
    expanded: list[dict] = []
    warnings: list[str] = []
    lexical = query
    if script_expansion != "none":
        if re.search(r'[:()|\\.*+?\[\]{}^$"\-]', query) or any(t.upper() in {"AND", "OR", "NOT"} for t in query.split()):
            raise ValueError("script expansion accepts plain terms only; put path restrictions in file_filter, or use raw Zoekt with script_expansion='none'")
        parts = []
        terms = query.split()
        if len(terms) > 16:
            raise ValueError("script expansion accepts at most 16 terms")
        for raw in terms:
            term = unicodedata.normalize("NFC", raw)
            scheme = script_expansion
            if scheme == "auto":
                scheme = "devanagari" if re.search(r"[\u0900-\u097f]", term) else "iast" if re.search(r"[āīūṛṝḷḹṅñṭḍṇśṣṃṁḥ]", term.casefold()) else "none"
            if scheme == "none":
                forms = [term]
                warnings.append(f"{term}: ASCII input was left unchanged; specify iast or harvard_kyoto for Sanskrit")
            else:
                dev = term if scheme == "devanagari" else to_devanagari(term, scheme)
                forms = list(dict.fromkeys(unicodedata.normalize("NFC", x) for x in [term, dev, from_devanagari(dev, "iast"), from_devanagari(dev, "harvard_kyoto")]))
            expanded.append({"input": raw, "forms": forms, "basis": "transliteration"})
            # Zoekt interprets alternatives as regex. Escape all literal forms.
            parts.append("(" + "|".join(re.escape(x) for x in forms) + ")")
        lexical = " ".join(parts)
    if file_filter:
        if len(file_filter.encode("utf-8")) > 1024:
            raise ValueError("file_filter must be at most 1024 UTF-8 bytes")
        # A quoted qualifier retains regex semantics while protecting spaces
        # and prevents a structured filter from injecting other operators.
        escaped = file_filter.replace("\\", "\\\\").replace('"', '\\"')
        lexical = f'({lexical}) file:"{escaped}"'
    if result_type == "files":
        lexical = f"({lexical}) type:filename"
    return lexical, expanded, warnings
