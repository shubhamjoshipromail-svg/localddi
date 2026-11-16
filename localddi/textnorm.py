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


# --------------------------------------------------------------------------- rewrites
#
# Names that reach an API from pharmacy systems are rarely the bare ingredient:
# "Metformin HCl", "Venlafaxine HCl ER", "Hydrocodone/Acetaminophen". The rules
# below are a fixed, ordered list of rewrites. Each is tried only when every
# earlier form failed to match RxNorm exactly, and the rule that matched is
# reported to the caller in the ``match`` field. Nothing here measures
# similarity: a misspelt name still does not match.

# Abbreviations expanded to the word RxNorm uses.
ABBREVIATIONS = {
    "hcl": "hydrochloride",
    "hbr": "hydrobromide",
    "hctz": "hydrochlorothiazide",
    "apap": "acetaminophen",
    "asa": "aspirin",
}

# Trailing words that describe a release form or device, not the drug.
FORM_WORDS = {
    "er", "xr", "xl", "sr", "cr", "dr", "la", "cd", "ec", "ir", "odt", "hfa",
    "12hr", "24hr", "extended", "delayed", "sustained", "release", "micronized",
}

# Trailing salt words. Dropped only as a last resort, and only when what is left
# is itself an RxNorm ingredient: RxNorm maps a salt to its base ingredient anyway.
SALT_WORDS = {
    "hydrochloride", "dihydrochloride", "hydrobromide", "sulfate", "sodium", "potassium",
    "calcium", "maleate", "tartrate", "bitartrate", "succinate", "fumarate", "besylate",
    "mesylate", "phosphate", "citrate", "bromide", "acetate", "base",
}

_COMBINATION_SPLIT = re.compile(r"\s*/\s*|\s+with\s+|\s+and\s+|(?<=[A-Za-z])-(?=[A-Za-z])", re.IGNORECASE)


def rewrites(name: str) -> list[tuple[str, str | None]]:
    """Forms of ``name`` to try, in order, as ``(normalised key, rule)``.

    The first entry has rule ``None`` (the name as given). Later entries are
    ``qualifier-stripped``, ``normalized`` (abbreviations expanded, release-form
    words dropped) and ``salt-stripped``.
    """
    forms: list[tuple[str, str | None]] = []

    def add(key: str, rule: str | None) -> None:
        if key and all(key != existing for existing, _ in forms):
            forms.append((key, rule))

    cleaned = name.strip().rstrip("*").strip()
    add(normalize_name(cleaned), None)
    stripped = strip_trailing_qualifier(cleaned)
    add(normalize_name(stripped), "qualifier-stripped")

    tokens = normalize_name(stripped).split()
    merged: list[str] = []
    for token in tokens:  # "di hcl" -> "dihydrochloride"
        if merged and merged[-1] == "di" and token in {"hcl", "hydrochloride"}:
            merged[-1] = "dihydrochloride"
        else:
            merged.append(ABBREVIATIONS.get(token, token))
    while len(merged) > 1 and merged[-1] in FORM_WORDS:
        merged.pop()
    add(" ".join(merged), "normalized")

    while len(merged) > 1 and merged[-1] in SALT_WORDS:
        merged.pop()
        add(" ".join(merged), "salt-stripped")
    return forms


def split_combination(name: str) -> list[str]:
    """Split ``"A/B"``, ``"A-B"``, ``"A with B"`` into parts; a single-part result means no split."""
    parts = [part.strip() for part in _COMBINATION_SPLIT.split(name.strip().rstrip("*")) if part.strip()]
    return parts if len(parts) > 1 else []
