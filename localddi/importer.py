"""Build the SQLite database from RxNorm plus one or more interaction sources.

The build is deterministic: the same input files always produce the same
tables. Nothing here calls a model or a web service.
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from . import db
from .rxnorm import RxNormData, tty_rank
from .textnorm import normalize_name, strip_trailing_qualifier

SEVERITIES = ("contraindicated", "major", "moderate", "minor", "unknown")
SEVERITY_RANK = {"unknown": 0, "minor": 1, "moderate": 2, "major": 3, "contraindicated": 4}

DDINTER_LICENSE = "CC BY-NC-SA 4.0"
DDINTER_LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
DDINTER_TERMS_URL = "https://ddinter2.scbdd.com/terms/"
DDINTER_ATTRIBUTION = (
    "Interaction data from DDInter 2.0 (https://ddinter2.scbdd.com), Computational Biology & Drug "
    "Design Group, Central South University, used under CC BY-NC-SA 4.0. Drug names were matched "
    "to RxNorm ingredients by localddi; rows that could not be matched were left out."
)
DDINTER_DISCLAIMER = (
    "DDInter data is licensed for non-commercial use only (CC BY-NC-SA 4.0). It is a research "
    "database and is not a substitute for professional medical judgement."
)


def normalize_severity(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    return value if value in SEVERITY_RANK else "unknown"


@dataclass
class InteractionRow:
    a_id: str
    a_name: str
    b_id: str
    b_name: str
    severity: str
    description: str | None = None
    management: str | None = None
    a_rxcui: str | None = None  # optional explicit RxCUIs (generic CSV only)
    b_rxcui: str | None = None


@dataclass
class Source:
    name: str
    license: str
    rows: Iterable[InteractionRow]
    version: str | None = None
    url: str | None = None
    license_url: str | None = None
    attribution: str | None = None
    disclaimer: str | None = None
    files: list[str] = field(default_factory=list)


@dataclass
class SourceReport:
    files: list[str] = field(default_factory=list)
    rows_read: int = 0
    unique_pairs: int = 0
    interactions_stored: int = 0
    pairs_dropped_unmatched_drug: int = 0
    pairs_dropped_same_ingredient: int = 0
    drugs_total: int = 0
    drugs_matched: int = 0
    match_kinds: dict[str, int] = field(default_factory=dict)
    severity_counts: dict[str, int] = field(default_factory=dict)
    unmatched_drugs: list[dict[str, str]] = field(default_factory=list)


# --------------------------------------------------------------------------- readers


def read_ddinter_dir(directory: Path) -> Iterator[InteractionRow]:
    """Read the DDInter download files (``ddinter_downloads_code_*.csv``)."""
    files = sorted(directory.glob("ddinter_downloads_code_*.csv"))
    if not files:
        raise FileNotFoundError(f"no ddinter_downloads_code_*.csv files in {directory}")
    for path in files:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"DDInterID_A", "Drug_A", "DDInterID_B", "Drug_B", "Level"}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError(f"{path} is missing columns {sorted(required - set(reader.fieldnames or []))}")
            for row in reader:
                yield InteractionRow(
                    a_id=row["DDInterID_A"].strip(),
                    a_name=row["Drug_A"].strip(),
                    b_id=row["DDInterID_B"].strip(),
                    b_name=row["Drug_B"].strip(),
                    severity=normalize_severity(row["Level"]),
                )


def read_generic_csv(path: Path) -> Iterator[InteractionRow]:
    """Read a bring-your-own-data CSV.

    Required columns: ``drug_a``, ``drug_b``. Optional: ``severity``,
    ``description``, ``management``, ``drug_a_id``, ``drug_b_id``,
    ``rxcui_a``, ``rxcui_b``.
    """
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"drug_a", "drug_b"}.issubset(reader.fieldnames or []):
            raise ValueError(f"{path} must have at least the columns drug_a and drug_b")
        for row in reader:
            a_name, b_name = (row.get("drug_a") or "").strip(), (row.get("drug_b") or "").strip()
            if not a_name or not b_name:
                continue
            yield InteractionRow(
                a_id=(row.get("drug_a_id") or "").strip() or normalize_name(a_name),
                a_name=a_name,
                b_id=(row.get("drug_b_id") or "").strip() or normalize_name(b_name),
                b_name=b_name,
                severity=normalize_severity(row.get("severity")),
                description=(row.get("description") or "").strip() or None,
                management=(row.get("management") or "").strip() or None,
                a_rxcui=(row.get("rxcui_a") or "").strip() or None,
                b_rxcui=(row.get("rxcui_b") or "").strip() or None,
            )


def ddinter_source(directory: Path) -> Source:
    return Source(
        name="DDInter",
        version="2.0",
        url="https://ddinter2.scbdd.com/",
        license=DDINTER_LICENSE,
        license_url=DDINTER_LICENSE_URL,
        attribution=DDINTER_ATTRIBUTION,
        disclaimer=DDINTER_DISCLAIMER,
        files=[path.name for path in sorted(directory.glob("ddinter_downloads_code_*.csv"))],
        rows=read_ddinter_dir(directory),
    )


def load_builtin_aliases() -> list[tuple[str, str]]:
    """(alias, RxNorm name) pairs shipped with the package."""
    text = resources.files("localddi").joinpath("data/aliases.csv").read_text(encoding="utf-8")
    pairs = []
    for row in csv.DictReader(line for line in text.splitlines() if line and not line.startswith("#")):
        pairs.append((row["alias"].strip(), row["rxnorm_name"].strip()))
    return pairs


# --------------------------------------------------------------------------- name index


class NameIndex:
    """Normalised name -> RxNorm concept, built once per import."""

    def __init__(self, rx: RxNormData, aliases: Iterable[tuple[str, str]] = ()):
        self.rx = rx
        self.entries: dict[str, dict[str, str]] = defaultdict(dict)  # norm -> {rxcui: origin}
        for name, rxcui in rx.names:
            key = normalize_name(name)
            if key:
                self.entries[key].setdefault(rxcui, "rxnorm")
        self.aliases_applied = 0
        for alias, target in aliases:
            key = normalize_name(alias)
            target_rxcui = self.best(normalize_name(target), origins={"rxnorm"})
            if key and target_rxcui and key not in self.entries:
                self.entries[key][target_rxcui] = "alias"
                self.aliases_applied += 1

    def best(self, norm: str, origins: set[str] | None = None) -> str | None:
        """Pick one concept for a key: ingredient first, then lowest RxCUI."""
        candidates = [
            rxcui
            for rxcui, origin in self.entries.get(norm, {}).items()
            if origins is None or origin in origins
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda rxcui: (tty_rank(self.rx.concepts[rxcui][1]), _numeric(rxcui)))

    def match_ingredient(self, name: str) -> tuple[str | None, str]:
        """Match a source's drug name to exactly one RxNorm ingredient.

        Returns ``(rxcui, kind)``. ``kind`` is how it matched (``exact``,
        ``alias``, ``qualifier-stripped``) or why it did not
        (``not-in-rxnorm``, ``multi-ingredient``).
        """
        reason = "not-in-rxnorm"
        attempts = [(name, None)]
        stripped = strip_trailing_qualifier(name)
        if stripped and stripped != name:
            attempts.append((stripped, "qualifier-stripped"))
        for text, forced_kind in attempts:
            norm = normalize_name(text)
            rxcui = self.best(norm)
            if rxcui is None:
                continue
            ingredients = self.rx.ingredients.get(rxcui, set())
            if len(ingredients) == 1:
                origin = self.entries[norm][rxcui]
                kind = forced_kind or ("alias" if origin == "alias" else "exact")
                return next(iter(ingredients)), kind
            reason = "multi-ingredient" if ingredients else reason
        return None, reason


def _numeric(rxcui: str) -> tuple[int, str]:
    return (int(rxcui), "") if rxcui.isdigit() else (10**12, rxcui)


# --------------------------------------------------------------------------- build


def build_database(
    out_path: Path,
    rx: RxNormData,
    sources: list[Source],
    aliases: Iterable[tuple[str, str]] | None = None,
) -> dict:
    """Write a fresh database to ``out_path`` (atomically) and return the import report."""
    index = NameIndex(rx, load_builtin_aliases() if aliases is None else aliases)
    tmp_path = out_path.with_name(out_path.name + ".building")
    conn = db.create(tmp_path)
    imported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report: dict = {
        "imported_at": imported_at,
        "rxnorm": {
            "version": rx.version,
            "concepts": len(rx.concepts),
            "ingredients": sum(1 for _, tty in rx.concepts.values() if tty == "IN"),
            "names": len(index.entries),
            "builtin_aliases_applied": index.aliases_applied,
        },
        "sources": {},
    }
    try:
        conn.executemany(
            "INSERT INTO concepts VALUES (?, ?, ?)",
            ((rxcui, name, tty) for rxcui, (name, tty) in rx.concepts.items()),
        )
        conn.executemany(
            "INSERT INTO ingredient_map VALUES (?, ?)",
            ((rxcui, ing) for rxcui, ings in rx.ingredients.items() for ing in sorted(ings)),
        )
        conn.executemany(
            "INSERT INTO names VALUES (?, ?, ?, ?)",
            (
                (norm, rxcui, rx.concepts[rxcui][1], origin)
                for norm, concepts in index.entries.items()
                for rxcui, origin in concepts.items()
            ),
        )
        for source in sources:
            report["sources"][source.name] = _import_source(conn, source, index, imported_at).__dict__
        totals = conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
        report["interactions_total"] = totals
        conn.execute("INSERT INTO meta VALUES ('imported_at', ?)", (imported_at,))
        conn.execute("INSERT INTO meta VALUES ('rxnorm_version', ?)", (rx.version or "unknown",))
        conn.execute("INSERT INTO meta VALUES ('report', ?)", (json.dumps(report),))
        conn.commit()
        conn.execute("VACUUM")
    except BaseException:
        conn.close()
        tmp_path.unlink(missing_ok=True)
        raise
    conn.close()
    os.replace(tmp_path, out_path)
    return report


def _import_source(conn, source: Source, index: NameIndex, imported_at: str) -> SourceReport:
    report = SourceReport(files=list(source.files))
    drugs: dict[str, tuple[str, str | None, str]] = {}  # source_id -> (name, rxcui, match kind)
    pairs: dict[tuple[str, str], InteractionRow] = {}

    def register(source_id: str, name: str, explicit_rxcui: str | None) -> None:
        if source_id in drugs:
            return
        if explicit_rxcui:
            ingredients = index.rx.ingredients.get(explicit_rxcui, set())
            if len(ingredients) == 1:
                drugs[source_id] = (name, next(iter(ingredients)), "rxcui")
                return
        rxcui, kind = index.match_ingredient(name)
        drugs[source_id] = (name, rxcui, kind)

    for row in source.rows:
        report.rows_read += 1
        register(row.a_id, row.a_name, row.a_rxcui)
        register(row.b_id, row.b_name, row.b_rxcui)
        key = (row.a_id, row.b_id) if row.a_id <= row.b_id else (row.b_id, row.a_id)
        existing = pairs.get(key)
        # Sources list the same pair more than once; keep the most severe statement.
        if existing is None or SEVERITY_RANK[row.severity] > SEVERITY_RANK[existing.severity]:
            pairs[key] = row
    report.unique_pairs = len(pairs)

    to_insert = []
    severity_counts: Counter[str] = Counter()
    for row in pairs.values():
        rxcui_a, rxcui_b = drugs[row.a_id][1], drugs[row.b_id][1]
        if rxcui_a is None or rxcui_b is None:
            report.pairs_dropped_unmatched_drug += 1
            continue
        if rxcui_a == rxcui_b:
            report.pairs_dropped_same_ingredient += 1
            continue
        a_id, b_id = row.a_id, row.b_id
        if rxcui_a > rxcui_b:
            rxcui_a, rxcui_b, a_id, b_id = rxcui_b, rxcui_a, b_id, a_id
        severity_counts[row.severity] += 1
        to_insert.append((source.name, a_id, b_id, rxcui_a, rxcui_b, row.severity, row.description, row.management))
    to_insert.sort()
    conn.executemany(
        "INSERT INTO interactions (source, a_source_id, b_source_id, rxcui_a, rxcui_b, severity, description, "
        "management) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        to_insert,
    )
    conn.executemany(
        "INSERT INTO source_drugs VALUES (?, ?, ?, ?, ?)",
        ((source.name, source_id, name, rxcui, kind) for source_id, (name, rxcui, kind) in sorted(drugs.items())),
    )
    # Make the source's own spellings searchable by name.
    extra_names = set()
    for name, rxcui, _ in drugs.values():
        key = normalize_name(name)
        if rxcui and key and rxcui not in index.entries.get(key, {}):
            extra_names.add((key, rxcui, "IN", source.name))
    conn.executemany("INSERT OR IGNORE INTO names VALUES (?, ?, ?, ?)", sorted(extra_names))
    conn.execute(
        "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            source.name, source.version, source.url, source.license, source.license_url,
            source.attribution, source.disclaimer, imported_at,
        ),
    )

    report.interactions_stored = len(to_insert)
    report.drugs_total = len(drugs)
    report.drugs_matched = sum(1 for _, rxcui, _ in drugs.values() if rxcui)
    report.match_kinds = dict(sorted(Counter(kind for _, _, kind in drugs.values()).items()))
    report.severity_counts = {name: severity_counts[name] for name in SEVERITIES if severity_counts[name]}
    report.unmatched_drugs = [
        {"source_id": source_id, "name": name, "reason": kind}
        for source_id, (name, rxcui, kind) in sorted(drugs.items())
        if rxcui is None
    ]
    return report
