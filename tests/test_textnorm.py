import pytest

from localddi.importer import normalize_severity
from localddi.textnorm import normalize_name, strip_trailing_qualifier


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Warfarin", "warfarin"),
        ("  WARFARIN  ", "warfarin"),
        ("Co-Trimoxazole", "co trimoxazole"),
        ("co  trimoxazole", "co trimoxazole"),
        ("St. John's Wort", "st john s wort"),
        ("Tylenol®", "tylenol"),
        ("Zoloft 50 mg", "zoloft 50 mg"),
        ("Acétaminophène", "acetaminophene"),
        ("simvastatin 40 MG Oral Tablet [Zocor]", "simvastatin 40 mg oral tablet zocor"),
        ("", ""),
        ("---", ""),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


def test_normalize_name_is_idempotent():
    once = normalize_name("  Amoxicillin / Clavulanate ")
    assert normalize_name(once) == once


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Acyclovir (topical)", "Acyclovir"),
        ("Dexamethasone (ophthalmic) ", "Dexamethasone"),
        ("Warfarin", "Warfarin"),
        ("Polyethylene glycol (3350 with electrolytes)", "Polyethylene glycol"),
        ("(only)", ""),
    ],
)
def test_strip_trailing_qualifier(raw, expected):
    assert strip_trailing_qualifier(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Major", "major"), (" moderate ", "moderate"), ("MINOR", "minor"), ("Unknown", "unknown"),
     ("Contraindicated", "contraindicated"), ("", "unknown"), (None, "unknown"), ("severe-ish", "unknown")],
)
def test_normalize_severity(raw, expected):
    assert normalize_severity(raw) == expected
