"""Read the RxNorm "Current Prescribable Content" release files.

Only two files are used:

* ``RXNCONSO.RRF`` - concept names. Columns (pipe-delimited, 0-based):
  0 RXCUI, 11 SAB, 12 TTY, 14 STR, 16 SUPPRESS.
* ``RXNREL.RRF`` - relationships. Columns: 0 RXCUI1, 4 RXCUI2, 7 RELA, 10 SAB.

Only rows with ``SAB=RXNORM`` are read. The relationship direction is never
relied on: an edge is used when the term types of its two ends form one of the
"towards the ingredient" steps in ``STEPS``, whichever way round it is stored.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

# Term types that define what a concept *is* (as opposed to synonym atoms).
CONCEPT_TTYS = {
    "IN", "PIN", "MIN", "BN",
    "SCDC", "SBDC", "SCDF", "SBDF", "SCDG", "SBDG", "SCDFP", "SBDFP",
    "SCD", "SBD", "GPCK", "BPCK",
}
# Synonym atoms: extra names for a concept that already has a concept term type.
SYNONYM_TTYS = {"SY", "TMSY", "PSN"}

# When several atoms of one RXCUI carry concept term types, the first of these wins.
TTY_PRIORITY = [
    "IN", "MIN", "PIN", "BN", "SCD", "SBD", "GPCK", "BPCK",
    "SCDC", "SBDC", "SCDF", "SBDF", "SCDFP", "SBDFP", "SCDG", "SBDG",
]
_PRIORITY = {tty: index for index, tty in enumerate(TTY_PRIORITY)}

# One step towards the ingredient: from a concept of the key type to a related
# concept of one of the listed types.
STEPS: dict[str, set[str]] = {
    "PIN": {"IN"},
    "MIN": {"IN"},
    "BN": {"IN"},
    "SCDC": {"IN"},
    "SBDC": {"SCDC"},
    "SCDF": {"IN"},
    "SCDFP": {"IN", "SCDF"},
    "SBDF": {"SCDF"},
    "SBDFP": {"SCDFP", "SBDF"},
    "SCDG": {"IN"},
    "SBDG": {"SCDG"},
    "SCD": {"SCDC"},
    "SBD": {"SCD", "SBDC"},
    "GPCK": {"SCD"},
    "BPCK": {"GPCK", "SBD", "SCD"},
}


def tty_rank(tty: str) -> int:
    return _PRIORITY.get(tty, len(_PRIORITY))


@dataclass
class RxNormData:
    version: str | None = None
    concepts: dict[str, tuple[str, str]] = field(default_factory=dict)  # rxcui -> (name, tty)
    names: set[tuple[str, str]] = field(default_factory=set)  # (raw name, rxcui)
    ingredients: dict[str, set[str]] = field(default_factory=dict)  # rxcui -> ingredient rxcuis


def _rows(lines: Iterable[str]) -> Iterator[list[str]]:
    for line in lines:
        line = line.rstrip("\n").rstrip("\r")
        if line:
            yield line.split("|")


def parse(conso_lines: Iterable[str], rel_lines: Iterable[str], version: str | None = None) -> RxNormData:
    """Build concepts, names and the concept -> ingredient map from RRF lines."""
    data = RxNormData(version=version)
    synonyms: list[tuple[str, str]] = []

    for row in _rows(conso_lines):
        if len(row) < 17 or row[11] != "RXNORM" or row[16] in {"O", "Y", "E"}:
            continue
        rxcui, tty, name = row[0], row[12], row[14]
        if tty in CONCEPT_TTYS:
            current = data.concepts.get(rxcui)
            if current is None or tty_rank(tty) < tty_rank(current[1]):
                data.concepts[rxcui] = (name, tty)
            data.names.add((name, rxcui))
        elif tty in SYNONYM_TTYS:
            synonyms.append((name, rxcui))

    for name, rxcui in synonyms:
        if rxcui in data.concepts:
            data.names.add((name, rxcui))

    next_steps: dict[str, set[str]] = defaultdict(set)
    for row in _rows(rel_lines):
        if len(row) < 11 or row[10] != "RXNORM":
            continue
        first, second = row[0], row[4]
        if first not in data.concepts or second not in data.concepts:
            continue
        tty_first, tty_second = data.concepts[first][1], data.concepts[second][1]
        if tty_second in STEPS.get(tty_first, ()):
            next_steps[first].add(second)
        if tty_first in STEPS.get(tty_second, ()):
            next_steps[second].add(first)

    for rxcui, (_, tty) in data.concepts.items():
        if tty == "IN":
            data.ingredients[rxcui] = {rxcui}
            continue
        found: set[str] = set()
        seen = {rxcui}
        stack = [rxcui]
        while stack:
            for neighbour in next_steps.get(stack.pop(), ()):
                if neighbour in seen:
                    continue
                seen.add(neighbour)
                if data.concepts[neighbour][1] == "IN":
                    found.add(neighbour)
                else:
                    stack.append(neighbour)
        if found:
            data.ingredients[rxcui] = found
    return data


def load_dir(directory: Path, version: str | None = None) -> RxNormData:
    """Load from a directory containing RXNCONSO.RRF and RXNREL.RRF."""
    conso, rel = directory / "RXNCONSO.RRF", directory / "RXNREL.RRF"
    for path in (conso, rel):
        if not path.exists():
            raise FileNotFoundError(f"{path} not found")
    with conso.open(encoding="utf-8") as conso_file, rel.open(encoding="utf-8") as rel_file:
        return parse(conso_file, rel_file, version=version)


def load_zip(zip_path: Path) -> RxNormData:
    """Load from an RxNorm release zip as downloaded from NLM."""
    with zipfile.ZipFile(zip_path) as archive:
        members = {Path(name).name: name for name in archive.namelist()}
        for needed in ("RXNCONSO.RRF", "RXNREL.RRF"):
            if needed not in members:
                raise ValueError(f"{zip_path} does not contain {needed}; is it an RxNorm release zip?")
        version = None
        for name in members:
            match = re.search(r"(\d{2})(\d{2})(\d{4})\.txt$", name)
            if name.lower().startswith("readme") and match:
                version = f"{match.group(3)}-{match.group(1)}-{match.group(2)}"
        with archive.open(members["RXNCONSO.RRF"]) as conso_raw, archive.open(members["RXNREL.RRF"]) as rel_raw:
            return parse(
                io.TextIOWrapper(conso_raw, encoding="utf-8"),
                io.TextIOWrapper(rel_raw, encoding="utf-8"),
                version=version,
            )
