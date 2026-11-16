"""Command-line behaviour, including the licence gate. No network is used."""

import json
from unittest.mock import Mock

import pytest

from localddi import cli, download
from tests.conftest import FIXTURES


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALDDI_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("LOCALDDI_DB", raising=False)
    return tmp_path


@pytest.fixture()
def forbid_downloads(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("this test must not download anything")

    monkeypatch.setattr(download, "fetch", refuse)


def test_demo_import_then_check(data_dir, forbid_downloads, capsys):
    assert cli.main(["import", "--demo"]) == 0
    assert (data_dir / "localddi.sqlite").exists()
    report = json.loads((data_dir / "import-report.json").read_text())
    assert report["interactions_total"] == 8
    capsys.readouterr()

    assert cli.main(["check", "warfarin", "aspirin", "207106", "warfarine"]) == 0
    out = capsys.readouterr().out
    assert "[MAJOR] warfarin + aspirin (DEMO)" in out
    assert "'warfarine' -> NOT RECOGNISED" in out
    assert "did you mean: warfarin" in out
    assert "NOT a medical device" in out

    assert cli.main(["status"]) == 0
    assert json.loads(capsys.readouterr().out)["interactions"] == 8


@pytest.mark.parametrize(("options", "host", "port", "url"), [
    ([], "127.0.0.1", 8080, "http://127.0.0.1:8080"),
    (["--host", "0.0.0.0", "--port", "8099"], "0.0.0.0", 8099, "http://localhost:8099"),
    (["--host", "::1"], "::1", 8080, "http://[::1]:8080"),
])
def test_demo_builds_fixture_then_serves(data_dir, forbid_downloads, monkeypatch, capsys, options, host, port, url):
    run = Mock()
    monkeypatch.setattr("uvicorn.run", run)
    assert cli.main(["demo", *options]) == 0
    assert (data_dir / "localddi.sqlite").exists()
    report = json.loads((data_dir / "import-report.json").read_text())
    assert report["interactions_total"] == 8
    assert list(report["sources"]) == ["DEMO"]
    assert url in capsys.readouterr().out
    run.assert_called_once_with("localddi.app:app", host=host, port=port, log_level="info")


def test_demo_preserves_existing_database(data_dir, forbid_downloads, monkeypatch, capsys):
    cli.main(["import", "--demo"])
    database = data_dir / "localddi.sqlite"
    original = database.read_bytes()
    original_report = (data_dir / "import-report.json").read_bytes()
    capsys.readouterr()
    run = Mock()
    monkeypatch.setattr("uvicorn.run", run)
    monkeypatch.setattr(cli, "cmd_import", Mock(side_effect=AssertionError("existing database must not be replaced")))
    assert cli.main(["demo"]) == 0
    assert database.read_bytes() == original
    assert (data_dir / "import-report.json").read_bytes() == original_report
    assert "Loading the bundled" not in capsys.readouterr().out
    run.assert_called_once()


def test_demo_respects_database_override(data_dir, forbid_downloads, monkeypatch):
    database = data_dir / "custom" / "demo.sqlite"
    monkeypatch.setenv("LOCALDDI_DB", str(database))
    monkeypatch.setattr("uvicorn.run", Mock())
    assert cli.main(["demo"]) == 0
    assert database.exists()
    assert not (data_dir / "localddi.sqlite").exists()


def test_demo_does_not_serve_after_failed_import(data_dir, monkeypatch):
    run = Mock()
    monkeypatch.setattr("uvicorn.run", run)
    monkeypatch.setattr(cli, "cmd_import", Mock(return_value=2))
    assert cli.main(["demo"]) == 2
    assert not (data_dir / "localddi.sqlite").exists()
    run.assert_not_called()


def test_check_reports_when_nothing_is_listed(data_dir, forbid_downloads, capsys):
    cli.main(["import", "--demo"])
    capsys.readouterr()
    cli.main(["check", "aspirin", "simvastatin"])
    assert "does not mean the combination is safe" in capsys.readouterr().out


def test_ddinter_needs_explicit_licence_acceptance(data_dir, forbid_downloads, capsys):
    """Without the flag (and without a terminal to ask on) nothing is downloaded or built."""
    assert cli.main(["import"]) == 2
    captured = capsys.readouterr()
    assert "CC BY-NC-SA 4.0" in captured.out
    assert "NonCommercial" in captured.out
    assert "--accept-ddinter-license" in captured.err
    assert not (data_dir / "localddi.sqlite").exists()


def test_import_from_local_files(data_dir, forbid_downloads, tmp_path, capsys):
    ddinter = tmp_path / "dd"
    ddinter.mkdir()
    (ddinter / "ddinter_downloads_code_A.csv").write_text(
        "DDInterID_A,Drug_A,DDInterID_B,Drug_B,Level\nDDInter1,Warfarin,DDInter2,Acetylsalicylic acid,Major\n",
        encoding="utf-8",
    )
    code = cli.main([
        "import", "--accept-ddinter-license",
        "--rxnorm-dir", str(FIXTURES / "rrf"), "--ddinter-dir", str(ddinter),
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "interactions stored               1" in captured.out
    # Only category A was supplied, so the other 13 are reported as missing.
    assert "WARNING: DDInter category file(s) B, C, D, G, H, J, L, M, N, P, R, S, V" in captured.err


def test_own_csv_without_ddinter(data_dir, forbid_downloads, tmp_path):
    mine = tmp_path / "mine.csv"
    mine.write_text("drug_a,drug_b,severity\nwarfarin,ibuprofen,major\n", encoding="utf-8")
    base = ["import", "--no-ddinter", "--rxnorm-dir", str(FIXTURES / "rrf"), "--csv", str(mine)]
    assert cli.main(base) == 2  # licence and name of the source are mandatory
    assert cli.main([*base, "--source-name", "Mine", "--source-license", "Proprietary"]) == 0
    report = json.loads((data_dir / "import-report.json").read_text())
    assert list(report["sources"]) == ["Mine"]


def test_no_ddinter_alone_is_an_error(data_dir, forbid_downloads):
    assert cli.main(["import", "--no-ddinter"]) == 2


def test_check_without_database(data_dir):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["check", "warfarin", "aspirin"])
    assert exit_info.value.code == 1
