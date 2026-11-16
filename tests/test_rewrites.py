"""Name rewrites: fixed rules for pharmacy-style names. Never similarity matching."""

import pytest

from localddi.textnorm import rewrites, split_combination


def keys(name):
    return [key for key, _ in rewrites(name)]


def test_plain_name_has_one_form():
    assert rewrites("warfarin") == [("warfarin", None)]


def test_abbreviation_and_release_form():
    assert rewrites("Sertraline HCl") == [
        ("sertraline hcl", None),
        ("sertraline hydrochloride", "normalized"),
        ("sertraline", "salt-stripped"),
    ]
    assert ("tramadol hydrochloride", "normalized") in rewrites("Tramadol HCl ER")
    assert ("pramipexole dihydrochloride", "normalized") in rewrites("Pramipexole Di-HCl")
    assert keys("Ibuprofen*")[0] == "ibuprofen"


def test_exact_form_is_always_tried_first():
    assert rewrites("warfarin sodium")[0] == ("warfarin sodium", None)
    assert rewrites("Acyclovir (topical)")[:2] == [("acyclovir topical", None), ("acyclovir", "qualifier-stripped")]


def test_a_single_word_is_never_stripped_away():
    assert keys("sodium") == ["sodium"]
    assert keys("ER") == ["er"]


def test_split_combination():
    assert split_combination("Oxycodone HCl/Acetaminophen") == ["Oxycodone HCl", "Acetaminophen"]
    assert split_combination("Oxycodone-Acetaminophen") == ["Oxycodone", "Acetaminophen"]
    assert split_combination("Acetaminophen With Codeine") == ["Acetaminophen", "Codeine"]
    assert split_combination("warfarin") == []
    assert split_combination("omega-3") == []


@pytest.mark.parametrize(
    ("name", "ingredients", "match"),
    [
        ("Sertraline HCl", {"sertraline"}, "normalized"),  # "sertraline hydrochloride" is in RxNorm
        ("Tramadol HCl ER", {"tramadol"}, "salt-stripped"),  # the fixture has no tramadol salt form
        ("Ibuprofen ER", {"ibuprofen"}, "normalized"),
        ("Fluconazole Sodium", {"fluconazole"}, "salt-stripped"),
        ("Warfarin Sodium*", {"warfarin"}, "exact"),
        ("Oxycodone HCl/Acetaminophen", {"oxycodone", "acetaminophen"}, "combination"),
        ("Acetaminophen-Oxycodone", {"oxycodone", "acetaminophen"}, "exact"),  # same key as RxNorm's "A / B"
        ("Warfarin with Aspirin", {"warfarin", "aspirin"}, "combination"),
        ("APAP", {"acetaminophen"}, "normalized"),
    ],
)
def test_rewritten_names_resolve(engine, name, ingredients, match):
    drug = engine.resolve_name(name)
    assert drug.resolved
    assert {c.name for c in drug.ingredients} == ingredients
    assert drug.match == match


def test_combination_uses_the_rxnorm_multi_ingredient_concept(engine):
    drug = engine.resolve_name("Oxycodone/Acetaminophen")
    assert drug.concept.rxcui == "214183"  # RxNorm's "acetaminophen / oxycodone"
    assert drug.concept.tty == "MIN"
    other = engine.resolve_name("Warfarin/Aspirin")  # no such RxNorm concept in the fixture
    assert other.resolved and other.concept is None
    assert other.as_dict()["rxcui"] is None


@pytest.mark.parametrize(
    "name",
    [
        "warfarine",  # misspelling
        "Warfarin/Notadrug",  # every part of a combination must resolve
        "Notadrug HCl",
        "Co-trimoxazole",  # "co" is not a drug, so the hyphen split fails
        "Zocor Sodium",  # salt stripping never lands on a brand name
    ],
)
def test_rewrites_do_not_invent_matches(engine, name):
    drug = engine.resolve_name(name)
    assert not drug.resolved
    assert drug.reason == "unknown-name"


def test_rxnorm_name_beats_a_source_spelling(engine):
    # "warfarin sodium" is an RxNorm salt form; the resolver must report that concept.
    assert engine.resolve_name("warfarin sodium").concept.tty == "PIN"


def test_combination_inputs_are_checked_ingredient_by_ingredient(client):
    body = client.get("/v1/interactions", params={"drugs": "Oxycodone HCl/Acetaminophen,Sertraline HCl"}).json()
    assert body["summary"]["complete"] is True
    assert body["summary"]["interactions_found"] == 1
    assert body["drugs"][0]["match"] == "combination"
    assert {c["name"] for c in body["drugs"][0]["ingredients"]} == {"acetaminophen", "oxycodone"}


def test_cli_prints_a_combination_without_an_rxcui(engine, tmp_path, monkeypatch, capsys):
    from localddi import cli

    monkeypatch.setenv("LOCALDDI_DATA_DIR", str(tmp_path))
    cli.main(["import", "--demo"])
    capsys.readouterr()
    cli.main(["check", "Warfarin/Aspirin", "ibuprofen"])
    out = capsys.readouterr().out
    assert "'Warfarin/Aspirin' -> aspirin, warfarin (combination)" in out
    assert "[MODERATE] warfarin + ibuprofen" in out
