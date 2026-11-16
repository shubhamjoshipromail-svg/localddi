"""The importer, run on the small synthetic fixture."""

import sqlite3

import pytest

from localddi import db
from localddi.importer import (
    NameIndex,
    Source,
    build_database,
    ddinter_source,
    read_ddinter_dir,
    read_generic_csv,
)
from tests.conftest import demo_source


def rows(path, sql, *params):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def test_report_counts(built):
    _, report = built
    demo = report["sources"]["DEMO"]
    assert demo["rows_read"] == 11
    assert demo["unique_pairs"] == 10  # simvastatin/fluconazole is listed twice
    assert demo["pairs_dropped_unmatched_drug"] == 1  # Notarealdrug
    assert demo["pairs_dropped_same_ingredient"] == 1  # albuterol vs salbutamol
    assert demo["interactions_stored"] == 8
    assert demo["drugs_total"] == 13
    assert demo["drugs_matched"] == 12
    assert demo["unmatched_drugs"] == [{"source_id": "DEMO11", "name": "Notarealdrug", "reason": "not-in-rxnorm"}]
    assert report["interactions_total"] == 8


def test_severity_counts(built):
    _, report = built
    assert report["sources"]["DEMO"]["severity_counts"] == {"major": 4, "moderate": 1, "minor": 2, "unknown": 1}


def test_duplicate_pair_keeps_highest_severity(db_file):
    found = rows(db_file, "SELECT severity FROM interactions WHERE rxcui_a = '36567' AND rxcui_b = '4450'")
    assert found == [("major",)]


def test_pairs_are_stored_in_canonical_order(db_file):
    assert rows(db_file, "SELECT COUNT(*) FROM interactions WHERE rxcui_a >= rxcui_b") == [(0,)]


def test_match_kinds(db_file):
    kinds = dict(rows(db_file, "SELECT name, match FROM source_drugs"))
    assert kinds["Warfarin"] == "exact"
    assert kinds["Acetylsalicylic acid"] == "alias"
    assert kinds["Salbutamol"] == "alias"
    assert kinds["Acyclovir (topical)"] == "qualifier-stripped"
    assert kinds["Notarealdrug"] == "not-in-rxnorm"


def test_alias_maps_to_the_rxnorm_ingredient(db_file):
    assert rows(db_file, "SELECT rxcui FROM source_drugs WHERE name = 'Acetylsalicylic acid'") == [("1191",)]


def test_source_metadata_is_stored(db_file):
    name, licence = rows(db_file, "SELECT name, license FROM sources")[0]
    assert (name, licence) == ("DEMO", "CC0-1.0")


def test_build_is_deterministic(tmp_path, rx):
    first, second = tmp_path / "a.sqlite", tmp_path / "b.sqlite"
    build_database(first, rx, [demo_source()])
    build_database(second, rx, [demo_source()])
    query = "SELECT source, a_source_id, b_source_id, rxcui_a, rxcui_b, severity FROM interactions ORDER BY id"
    assert rows(first, query) == rows(second, query)
    assert rows(first, "SELECT * FROM names ORDER BY 1, 2, 3") == rows(second, "SELECT * FROM names ORDER BY 1, 2, 3")


def test_rebuild_replaces_database_atomically(tmp_path, rx):
    path = tmp_path / "localddi.sqlite"
    build_database(path, rx, [demo_source()])
    build_database(path, rx, [])
    assert rows(path, "SELECT COUNT(*) FROM interactions") == [(0,)]
    assert not (tmp_path / "localddi.sqlite.building").exists()


def test_multi_ingredient_name_is_not_matched(rx):
    index = NameIndex(rx, [])
    assert index.match_ingredient("Percocet") == (None, "multi-ingredient")
    assert index.match_ingredient("Tylenol") == ("161", "exact")
    assert index.match_ingredient("warfarin sodium") == ("11289", "exact")


def test_alias_never_overrides_an_rxnorm_name(rx):
    index = NameIndex(rx, [("aspirin", "warfarin"), ("coumadine", "warfarin"), ("x", "not in rxnorm")])
    assert index.match_ingredient("aspirin") == ("1191", "exact")
    assert index.match_ingredient("Coumadine") == ("11289", "alias")
    assert index.aliases_applied == 1


def test_ddinter_format(tmp_path, rx):
    """A file in DDInter's download format, with made-up rows."""
    (tmp_path / "ddinter_downloads_code_A.csv").write_text(
        "DDInterID_A,Drug_A,DDInterID_B,Drug_B,Level\n"
        "DDInter1,Warfarin,DDInter2,Acetylsalicylic acid,Major\n"
        "DDInter3,Acyclovir (topical),DDInter1,Warfarin,Unknown\n",
        encoding="utf-8",
    )
    (tmp_path / "ddinter_downloads_code_B.csv").write_text(
        "DDInterID_A,Drug_A,DDInterID_B,Drug_B,Level\n"
        "DDInter2,Acetylsalicylic acid,DDInter1,Warfarin,Major\n"
        "DDInter4,Madeupium,DDInter1,Warfarin,Minor\n",
        encoding="utf-8",
    )
    parsed = list(read_ddinter_dir(tmp_path))
    assert len(parsed) == 4
    assert parsed[0].severity == "major"

    out = tmp_path / "out.sqlite"
    report = build_database(out, rx, [ddinter_source(tmp_path)])["sources"]["DDInter"]
    assert report["rows_read"] == 4
    assert report["unique_pairs"] == 3
    assert report["interactions_stored"] == 2
    assert report["pairs_dropped_unmatched_drug"] == 1
    licence = rows(out, "SELECT license FROM sources WHERE name = 'DDInter'")
    assert licence == [("CC BY-NC-SA 4.0",)]


def test_ddinter_reader_rejects_wrong_columns(tmp_path):
    (tmp_path / "ddinter_downloads_code_A.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        list(read_ddinter_dir(tmp_path))


def test_ddinter_reader_needs_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(read_ddinter_dir(tmp_path))


def test_generic_csv_with_explicit_rxcuis(tmp_path, rx):
    csv_path = tmp_path / "mine.csv"
    csv_path.write_text(
        "drug_a,drug_b,severity,rxcui_a,rxcui_b\n"
        "House name for Zocor,my fluconazole,contraindicated,196503,4450\n"
        ",missing name,major,,\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.sqlite"
    source = Source(name="Mine", license="Proprietary", rows=read_generic_csv(csv_path))
    report = build_database(out, rx, [source])["sources"]["Mine"]
    assert report["rows_read"] == 1
    assert report["interactions_stored"] == 1
    # The brand RxCUI was reduced to its ingredient.
    assert rows(out, "SELECT rxcui_a, rxcui_b, severity FROM interactions") == [("36567", "4450", "contraindicated")]


def test_generic_csv_needs_drug_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("x,y\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="drug_a and drug_b"):
        list(read_generic_csv(bad))


def test_database_opens_read_only(db_file):
    conn = db.open_readonly(db_file)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM interactions")
    conn.close()


def test_open_readonly_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        db.open_readonly(tmp_path / "nope.sqlite")
