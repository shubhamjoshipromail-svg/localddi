"""Shared fixtures. Everything runs offline against the bundled synthetic fixture."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from localddi import db, rxnorm
from localddi.app import create_app
from localddi.engine import Engine
from localddi.importer import Source, build_database, read_generic_csv

FIXTURES = Path(str(resources.files("localddi").joinpath("fixtures")))


@pytest.fixture(scope="session")
def rx():
    return rxnorm.load_dir(FIXTURES / "rrf", version="demo-fixture")


def demo_source() -> Source:
    return Source(
        name="DEMO",
        version="fixture",
        license="CC0-1.0",
        attribution="Synthetic demo rows.",
        disclaimer="DEMO DATA.",
        rows=read_generic_csv(FIXTURES / "demo_interactions.csv"),
    )


@pytest.fixture(scope="session")
def built(tmp_path_factory, rx):
    """(database path, import report) for the demo fixture."""
    path = tmp_path_factory.mktemp("db") / "localddi.sqlite"
    report = build_database(path, rx, [demo_source()])
    return path, report


@pytest.fixture(scope="session")
def db_file(built):
    return built[0]


@pytest.fixture()
def engine(db_file):
    conn = db.open_readonly(db_file)
    yield Engine(conn)
    conn.close()


@pytest.fixture()
def client(db_file, monkeypatch):
    monkeypatch.delenv("LOCALDDI_API_KEY", raising=False)
    return TestClient(create_app(db_file))
