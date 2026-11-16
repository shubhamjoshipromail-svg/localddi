"""RxNorm parsing: concept types and the concept -> ingredient map."""

from localddi import rxnorm


def test_concepts_have_expected_types(rx):
    assert rx.concepts["11289"] == ("warfarin", "IN")
    assert rx.concepts["196503"] == ("Zocor", "BN")
    assert rx.concepts["152923"] == ("simvastatin 40 MG Oral Tablet [Zocor]", "SBD")
    assert rx.concepts["114194"] == ("warfarin sodium", "PIN")


def test_ingredient_maps_to_itself(rx):
    assert rx.ingredients["11289"] == {"11289"}


def test_brand_name_maps_to_ingredient(rx):
    assert rx.ingredients["196503"] == {"36567"}  # Zocor -> simvastatin
    assert rx.ingredients["202433"] == {"161"}  # Tylenol -> acetaminophen


def test_branded_tablet_maps_to_ingredient(rx):
    assert rx.ingredients["152923"] == {"36567"}  # Zocor 40 MG tablet -> simvastatin
    assert rx.ingredients["207106"] == {"4450"}  # Diflucan 50 MG tablet -> fluconazole


def test_salt_form_maps_to_base_ingredient(rx):
    assert rx.ingredients["114194"] == {"11289"}  # warfarin sodium -> warfarin


def test_combination_products_map_to_every_ingredient(rx):
    expected = {"161", "7804"}  # acetaminophen + oxycodone
    assert rx.ingredients["42844"] == expected  # Percocet (BN)
    assert rx.ingredients["214183"] == expected  # acetaminophen / oxycodone (MIN)
    assert rx.ingredients["1049625"] == expected  # Percocet tablet (SBD)


def test_every_fixture_concept_reaches_an_ingredient(rx):
    assert set(rx.concepts) == set(rx.ingredients)


def test_relationship_direction_does_not_matter():
    conso = [
        "1|ENG||||||A1||||RXNORM|IN|1|drugone||N||",
        "2|ENG||||||A2||||RXNORM|BN|2|Brandone||N||",
    ]
    forward = ["1||CUI|RO|2||CUI|has_tradename|R1||RXNORM||||N||"]
    backward = ["2||CUI|RO|1||CUI|tradename_of|R1||RXNORM||||N||"]
    assert rxnorm.parse(conso, forward).ingredients["2"] == {"1"}
    assert rxnorm.parse(conso, backward).ingredients["2"] == {"1"}


def test_non_rxnorm_and_obsolete_rows_are_ignored():
    conso = [
        "1|ENG||||||A1||||RXNORM|IN|1|drugone||N||",
        "5|ENG||||||A5||||MTHSPL|SU|5|OTHER SOURCE||N||",
        "6|ENG||||||A6||||RXNORM|IN|6|olddrug||O||",
    ]
    data = rxnorm.parse(conso, [])
    assert set(data.concepts) == {"1"}


def test_synonym_adds_a_name_but_not_a_concept():
    conso = [
        "1|ENG||||||A1||||RXNORM|IN|1|drugone||N||",
        "1|ENG||||||A2||||RXNORM|SY|1|drug-1||N||",
        "9|ENG||||||A9||||RXNORM|SY|9|orphan synonym||N||",
    ]
    data = rxnorm.parse(conso, [])
    assert data.names == {("drugone", "1"), ("drug-1", "1")}


def test_load_zip_reads_version_from_readme(tmp_path, rx):
    import zipfile
    from pathlib import Path

    from tests.conftest import FIXTURES

    archive = tmp_path / "rx.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("Readme_Full_Prescribe_11022026.txt", "readme")
        for name in ("RXNCONSO.RRF", "RXNREL.RRF"):
            handle.write(Path(FIXTURES) / "rrf" / name, f"rrf/{name}")
    data = rxnorm.load_zip(archive)
    assert data.version == "2026-11-02"
    assert data.concepts == rx.concepts
    assert data.ingredients == rx.ingredients
