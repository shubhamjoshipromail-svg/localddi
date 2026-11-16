"""SQLite storage. The server opens the file read-only; only the importer writes."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1"

SCHEMA = """
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row per RxNorm concept (ingredient, brand, clinical drug, ...).
CREATE TABLE concepts (
    rxcui TEXT PRIMARY KEY,
    name  TEXT NOT NULL,
    tty   TEXT NOT NULL
);

-- Every concept mapped to the ingredient(s) it contains. Ingredients map to themselves.
CREATE TABLE ingredient_map (
    rxcui            TEXT NOT NULL,
    ingredient_rxcui TEXT NOT NULL,
    PRIMARY KEY (rxcui, ingredient_rxcui)
) WITHOUT ROWID;

-- Normalised name -> concept. origin is 'rxnorm', 'alias' (built-in synonym list)
-- or the name of an interaction source whose spelling was matched at import.
CREATE TABLE names (
    norm   TEXT NOT NULL,
    rxcui  TEXT NOT NULL,
    tty    TEXT NOT NULL,
    origin TEXT NOT NULL,
    PRIMARY KEY (norm, rxcui, origin)
) WITHOUT ROWID;

CREATE TABLE sources (
    name        TEXT PRIMARY KEY,
    version     TEXT,
    url         TEXT,
    license     TEXT NOT NULL,
    license_url TEXT,
    attribution TEXT,
    disclaimer  TEXT,
    imported_at TEXT NOT NULL
);

-- Drugs as the interaction source names them, with the RxNorm ingredient they
-- were matched to (NULL when no match was found).
CREATE TABLE source_drugs (
    source    TEXT NOT NULL,
    source_id TEXT NOT NULL,
    name      TEXT NOT NULL,
    rxcui     TEXT,
    match     TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
) WITHOUT ROWID;

-- One row per asserted interaction between two ingredients. rxcui_a < rxcui_b (string order).
CREATE TABLE interactions (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    a_source_id TEXT NOT NULL,
    b_source_id TEXT NOT NULL,
    rxcui_a     TEXT NOT NULL,
    rxcui_b     TEXT NOT NULL,
    severity    TEXT NOT NULL,
    description TEXT,
    management  TEXT
);
CREATE INDEX interactions_a_idx ON interactions (rxcui_a, rxcui_b);
CREATE INDEX interactions_b_idx ON interactions (rxcui_b);
"""


def create(path: Path) -> sqlite3.Connection:
    """Create a fresh database file with the schema applied."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
    return conn


def open_readonly(path: Path) -> sqlite3.Connection:
    """Open the database read-only. Raises FileNotFoundError if nothing was imported."""
    if not path.exists():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
