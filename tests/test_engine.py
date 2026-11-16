"""Edge cases of pair selection that the shared fixture does not reach."""

import pytest

from localddi import db
from localddi.engine import Engine
from localddi.importer import Source, build_database, read_generic_csv


@pytest.fixture()
def combo_engine(tmp_path, rx):
    """A database where the two ingredients of Percocet are listed as interacting."""
    csv_path = tmp_path / "combo.csv"
    csv_path.write_text("drug_a,drug_b,severity\nacetaminophen,oxycodone,minor\n", encoding="utf-8")
    path = tmp_path / "combo.sqlite"
    build_database(path, rx, [Source(name="T", license="CC0-1.0", rows=read_generic_csv(csv_path))])
    conn = db.open_readonly(path)
    yield Engine(conn)
    conn.close()


def test_ingredients_of_one_product_are_not_checked_against_each_other(combo_engine):
    percocet = combo_engine.resolve_name("Percocet")
    assert combo_engine.between([percocet]) == []
    assert combo_engine.for_drug(percocet) == []


def test_the_same_product_twice_is_not_an_interaction(combo_engine):
    first, second = combo_engine.resolve_name("Percocet"), combo_engine.resolve_rxcui("1049625")
    assert combo_engine.between([first, second]) == []


def test_product_against_one_of_its_own_ingredients_is_reported(combo_engine):
    """Percocet plus separate oxycodone: the acetaminophen-oxycodone row applies across the two inputs."""
    findings = combo_engine.between([combo_engine.resolve_name("Percocet"), combo_engine.resolve_name("oxycodone")])
    assert [(f.ingredient_a.name, f.ingredient_b.name) for f in findings] == [("acetaminophen", "oxycodone")]
    assert findings[0].drug_a.input == "Percocet"
    assert findings[0].drug_b.input == "oxycodone"


def test_unresolved_drugs_are_ignored_by_pair_selection(combo_engine):
    drugs = [combo_engine.resolve_name("nonsense"), combo_engine.resolve_name("oxycodone")]
    assert combo_engine.between(drugs) == []
    assert combo_engine.for_drug(drugs[0]) == []
