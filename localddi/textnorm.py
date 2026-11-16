"""Deterministic text normalisation for drug names.

The same function is used when names are indexed at import time and when a
query arrives, so matching is an exact lookup on the normalised key. There is
no fuzzy matching in the lookup path; suggestions are offered separately and
are never applied automatically.
"""

from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_TRAILING_PAREN = re.compile(r"\s*\([^()]*\)\s*$")


def normalize_name(value: str) -> str:
    """Return the lookup key for a drug name.

    Lower-cases, strips accents, turns every run of non-alphanumeric
    characters into one space and trims. ``"  Co-Trimoxazole "`` and
    ``"co trimoxazole"`` therefore share a key.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM.sub(" ", ascii_only.lower()).strip()


def strip_trailing_qualifier(value: str) -> str:
    """Drop one trailing parenthetical, e.g. ``"Acyclovir (topical)"`` -> ``"Acyclovir"``.

    Interaction sources often qualify a drug by route. RxNorm ingredients are
    route-independent, so the importer falls back to the unqualified name.
    """
    return _TRAILING_PAREN.sub("", value).strip()
