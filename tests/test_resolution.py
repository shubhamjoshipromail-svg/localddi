"""Name and RxCUI resolution at query time."""

import pytest


@pytest.mark.parametrize(
    ("name", "rxcui", "match"),
    [
        ("warfarin", "11289", "exact"),
        ("  WARFARIN ", "11289", "exact"),
        ("Zocor", "196503", "exact"),
        ("tylenol", "202433", "exact"),
        ("warfarin sodium", "114194", "exact"),
        ("simvastatin 40 mg oral tablet [zocor]", "152923", "exact"),
        ("acetylsalicylic acid", "1191", "alias"),
        ("Paracetamol", "161", "alias"),
        ("salbutamol", "435", "alias"),
        ("Acyclovir (topical)", "281", "source-name"),
        ("Ibuprofen (oral)", "5640", "qualifier-stripped"),
    ],
)
def test_names_resolve(engine, name, rxcui, match):
    drug = engine.resolve_name(name)
    assert drug.resolved
    assert drug.concept.rxcui == rxcui
    assert drug.match == match


def test_brand_resolves_to_its_ingredient(engine):
    drug = engine.resolve_name("Zocor")
    assert [(c.rxcui, c.name) for c in drug.ingredients] == [("36567", "simvastatin")]


def test_combination_brand_resolves_to_all_ingredients(engine):
    drug = engine.resolve_name("Percocet")
    assert {c.name for c in drug.ingredients} == {"acetaminophen", "oxycodone"}


def test_misspelling_is_not_matched_but_suggested(engine):
    drug = engine.resolve_name("warfarine")
    assert not drug.resolved
    assert drug.reason == "unknown-name"
    assert drug.concept is None
    assert "warfarin" in drug.suggestions


def test_unknown_name_without_close_match(engine):
    drug = engine.resolve_name("zzzzqqqq")
    assert not drug.resolved
    assert drug.suggestions == []


@pytest.mark.parametrize("name", ["", "   ", "--"])
def test_empty_names_do_not_resolve(engine, name):
    assert not engine.resolve_name(name).resolved


def test_rxcui_resolution(engine):
    drug = engine.resolve_rxcui("207106")
    assert drug.resolved
    assert drug.concept.tty == "SBD"
    assert [c.rxcui for c in drug.ingredients] == ["4450"]


def test_unknown_rxcui(engine):
    drug = engine.resolve_rxcui("999999999")
    assert not drug.resolved
    assert drug.reason == "unknown-rxcui"


def test_resolution_is_stable(engine):
    first = [engine.resolve_name("zocor").as_dict() for _ in range(3)]
    assert first[0] == first[1] == first[2]
