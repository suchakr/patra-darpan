"""Deterministic nakṣatra name correction for OCR/VLM output.

This module provides a canonical lookup table for the 27+1 traditional
nakṣatra names in IAST transliteration.  It covers known OCR and PDF
encoding variants observed across the micro-5 corpus:

- Underdot loss: ṛ→r, ṇ→n, ṣ→s, ṭ→t, ḍ→d
- Cedilla substitution: ş/ș→ṣ, ţ/ț→ṭ, ņ→ṇ
- Circumflex substitution: â→ā, î→ī, û→ū (PGondhalekar encoding)
- Miscellaneous: ƒ ligatures, missing śa, missing macrons

The lookup is intentionally conservative: it only corrects nakṣatra names
and a small set of closely related astronomical Sanskrit terms.  It does
not attempt general IAST correction.

Usage::

    from lib.decode_lab.nakshatra_lookup import apply_nakshatra_corrections
    corrected = apply_nakshatra_corrections(gemini_output_text)
"""

from __future__ import annotations


# Canonical IAST spellings for the 27 nakṣatras + Abhijit.
# Each key is a known OCR/encoding variant; value is the correct IAST form.
# Multiple keys may map to the same canonical value.
NAKSHATRA_VARIANTS: dict[str, str] = {
    # 1. Kṛttikā
    "Krttikā": "Kṛttikā",
    "Krttikâ": "Kṛttikā",
    "kṛttikâ": "kṛttikā",
    # 2. Rohiṇī
    "Rohinī": "Rohiṇī",
    "Rohini": "Rohiṇī",
    "rohiņi": "rohiṇī",
    "rohinī": "rohiṇī",
    # 3. Mṛgaśira / Mṛgaśirṣā
    "Mrgaśira": "Mṛgaśira",
    "Mrgaśirṣa": "Mṛgaśirṣā",
    "mṛgasirsa": "mṛgaśirṣā",
    "mṛgasirṣa": "mṛgaśirṣā",
    # 4. Ārdrā
    "Ârdrâ": "Ārdrā",
    "ârdrâ": "ārdrā",
    # 5. Punarvasu (usually correct)
    "punarvasū": "punarvasū",
    # 6. Puṣya
    "Pusya": "Puṣya",
    "Puşya": "Puṣya",
    # 7. Āśleṣā
    "Asleṣā": "Āśleṣā",
    "Aslesā": "Āśleṣā",
    "Âśleṣâ": "Āśleṣā",
    "âśleṣâ": "āśleṣā",
    # 8. Maghā
    "Mâgha": "Māghā",
    "maghâ": "maghā",
    # 9–10. Phālgunī (Pūrva / Uttara)
    "Phalgunī": "Phālgunī",
    "Phâlgunî": "Phālgunī",
    "phâlguņi": "phālgunī",
    "phālguņi": "phālgunī",
    # 11. Hasta (usually correct)
    # 12. Citrā
    "Citrâ": "Citrā",
    "citrâ": "citrā",
    # 13. Svātī
    "Svâti": "Svātī",
    "svâti": "svātī",
    # 14. Viśākhā / Viśākhe (dual)
    "Viśâkhe": "Viśākhe",
    "viśâkhe": "viśākhe",
    "Visƒâkhe": "Viśākhe",
    # 15. Anūrādhā
    "Anurādhā": "Anūrādhā",
    "Anurâdhâ": "Anūrādhā",
    "anurâdhâ": "anurādhā",
    # 16. Jyeṣṭhā
    "Jyesthā": "Jyeṣṭhā",
    "Jyeşthā": "Jyeṣṭhā",
    "Jyeṣṭhâ": "Jyeṣṭhā",
    "jyeṣṭhâ": "jyeṣṭhā",
    # 17. Mūla (usually correct)
    # 18–19. Aṣāḍhā (Pūrva / Uttara)
    "Aṣādhā": "Aṣāḍhā",
    "Aşādhā": "Aṣāḍhā",
    "Aṣâdhâ": "Āṣāḍhā",
    "âṣâdhâ": "āṣāḍhā",
    # ** Abhijit (usually correct)
    # 20. Śravaṇa
    "Sravaṇa": "Śravaṇa",
    "Śravaņa": "Śravaṇa",
    # 21. Śraviṣṭhā / Dhaniṣṭhā
    "Sraviṣṭhā": "Śraviṣṭhā",
    "Śravișṭhā": "Śraviṣṭhā",
    "śravisthâ": "śraviṣṭhā",
    "Sravisthâ": "Śraviṣṭhā",
    "Dhanișṭhā": "Dhaniṣṭhā",
    # 22. Śatabhiṣak / Śatabhiṣaj
    "Satabhiṣak": "Śatabhiṣak",
    "Satabhiṣaj": "Śatabhiṣaj",
    # 23–24. Proṣṭhapadā (Pūrva / Uttara)
    "Prosthapadā": "Proṣṭhapadā",
    "Proşthapadā": "Proṣṭhapadā",
    "Proṣṭapadâ": "Proṣṭhapadā",
    "proṣṭapadâ": "proṣṭhapadā",
    # 25. Revatī
    "Revati": "Revatī",
    "revati": "revatī",
    # 26. Aśvayuk / Aśvayujau (dual)
    "Asvayujau": "Aśvayujau",
    "asvayujau": "aśvayujau",
    # 27. Bharaṇī
    "Bharanī": "Bharaṇī",
    "Bharani": "Bharaṇī",
    "bharaņi": "bharaṇī",
}

# Related Sanskrit astronomical terms that appear in tables.
TERM_VARIANTS: dict[str, str] = {
    "Simhaniṣadya": "Siṁhaniṣadya",
    "Simhanisaḍya": "Siṁhaniṣadya",
    "yogatârâs": "yogatārās",
    "yogatâra": "yogatārā",
    "naks. atra": "nakṣatra",
    "naks. atras": "nakṣatras",
}


def apply_nakshatra_corrections(text: str) -> str:
    """Apply deterministic nakṣatra and term corrections to *text*.

    Returns the corrected text.  Only performs exact string replacements
    from the known variant tables — no regex, no inference.
    """
    for variant, canonical in NAKSHATRA_VARIANTS.items():
        if variant != canonical and variant in text:
            text = text.replace(variant, canonical)
    for variant, canonical in TERM_VARIANTS.items():
        if variant != canonical and variant in text:
            text = text.replace(variant, canonical)
    return text
