#!/usr/bin/env python3
"""Measure a localddi database against three public references.

    python scripts/evaluate.py                # uses $LOCALDDI_DATA_DIR/localddi.sqlite
    python scripts/evaluate.py --json out.json

The references are downloaded when the script runs and cached under
``<data dir>/evaluation-cache``. They are not part of this repository:

1. ONC high-priority drug-drug interactions (Phansalkar et al., JAMIA 2012), as
   expanded to individual drug pairs by the University of Pittsburgh group
   (github.com/dbmi-pitt/public-PDDI-analysis). This is the list NLM served as "ONCHigh".
2. Real responses of the NLM interaction API preserved by the Internet Archive
   (scripts/nlm_captures.tsv): what NLM actually returned, mostly from DrugBank.
3. The drug names in CMS's "Medicare Part D Spending by Drug" file (US government
   data), ranked by 2024 claims: do the names pharmacies actually send resolve?

What this does NOT measure is clinical correctness. See docs/evaluation.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from localddi import config, db  # noqa: E402
from localddi.download import fetch  # noqa: E402
from localddi.engine import Engine  # noqa: E402

ONC_URL = (
    "https://raw.githubusercontent.com/dbmi-pitt/public-PDDI-analysis/master/"
    "PDDI-Datasets/ONC-High-Priority/ONC_High_Priority_Mapped.csv"
)
PARTD_URL = (
    "https://data.cms.gov/sites/default/files/2026-06/98218f98-166c-4723-8438-c344a4ef96a6/"
    "DSD_PTD_RY26_P04_V10_DY24_BGM.csv"
)
WAYBACK = "https://web.archive.org/web/{timestamp}id_/{url}"
CAPTURES = Path(__file__).with_name("nlm_captures.tsv")


def cached(url: str, dest: Path, pause: float = 0.0) -> Path:
    if not dest.exists():
        print(f"  fetching {url[:100]}", file=sys.stderr)
        fetch(url, dest)
        time.sleep(pause)
    return dest


# --------------------------------------------------------------------------- 1. ONC high priority


def evaluate_onc(engine: Engine, cache: Path) -> dict:
    path = cached(ONC_URL, cache / "onc_high_priority_mapped.csv")
    pairs = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        fields = line.split("$")
        if len(fields) >= 4 and fields[0].strip() and fields[2].strip():
            pair = frozenset((fields[0].strip(), fields[2].strip()))
            if len(pair) == 2:
                pairs.add(pair)

    resolved = {name: engine.resolve_name(name) for pair in pairs for name in pair}
    known_to_sources = {
        name: all(
            engine.conn.execute("SELECT 1 FROM source_drugs WHERE rxcui = ?", (c.rxcui,)).fetchone()
            for c in drug.ingredients
        )
        for name, drug in resolved.items()
        if drug.resolved
    }
    result = {"pairs": len(pairs), "drugs": len(resolved)}
    severity: Counter[str] = Counter()
    outcome: Counter[str] = Counter()
    not_listed: list[list[str]] = []
    for pair in sorted(tuple(sorted(p)) for p in pairs):
        first, second = (resolved[name] for name in pair)
        if not (first.resolved and second.resolved):
            outcome["untestable_drug_not_in_rxnorm"] += 1
            continue
        findings = engine.between([first, second])
        if findings:
            outcome["listed"] += 1
            severity[findings[0].severity] += 1
        else:
            both_known = known_to_sources[pair[0]] and known_to_sources[pair[1]]
            outcome["not_listed_both_drugs_in_source" if both_known else "not_listed_drug_absent_from_source"] += 1
            not_listed.append(list(pair))
    testable = len(pairs) - outcome["untestable_drug_not_in_rxnorm"]
    result.update(
        testable_pairs=testable,
        outcome=dict(outcome),
        listed_by_severity=dict(severity),
        recall_of_testable=round(outcome["listed"] / testable, 4) if testable else None,
        recall_as_major_or_worse=round((severity["major"] + severity["contraindicated"]) / testable, 4),
        drugs_not_in_rxnorm=sorted(name for name, drug in resolved.items() if not drug.resolved),
        drugs_most_often_in_unlisted_pairs=Counter(n for pair in not_listed for n in pair).most_common(8),
        pairs_not_listed=not_listed,
    )
    return result


# --------------------------------------------------------------------------- 2. archived NLM responses


def parse_nlm(body: str) -> list[tuple[str, str, str, str]]:
    """(source, severity, rxcui, rxcui) for every interactionPair in an NLM response, JSON or XML."""
    rows = []
    if body.lstrip().startswith("{"):
        data = json.loads(body)
        for group in data.get("interactionTypeGroup", []) + data.get("fullInteractionTypeGroup", []):
            for item in group.get("interactionType", []) + group.get("fullInteractionType", []):
                for pair in item["interactionPair"]:
                    first, second = (c["minConceptItem"]["rxcui"] for c in pair["interactionConcept"])
                    rows.append((group["sourceName"], pair["severity"], first, second))
    else:
        for group in ET.fromstring(body).iter():
            if group.tag in ("interactionTypeGroup", "fullInteractionTypeGroup"):
                for pair in group.iter("interactionPair"):
                    ids = [c.findtext("minConceptItem/rxcui") for c in pair.findall("interactionConcept")]
                    rows.append((group.findtext("sourceName"), pair.findtext("severity"), ids[0], ids[1]))
    return rows


def evaluate_nlm_archive(engine: Engine, cache: Path) -> dict:
    captures = [
        line.split("\t") for line in CAPTURES.read_text().splitlines() if line and not line.startswith("#")
    ]
    reference: dict[tuple[str, frozenset[str]], str] = {}
    non_empty = 0
    for index, (timestamp, url) in enumerate(captures, start=1):
        path = cached(WAYBACK.format(timestamp=timestamp, url=url), cache / "nlm" / f"{index:02d}.body", pause=2)
        rows = parse_nlm(path.read_text(encoding="utf-8", errors="replace"))
        non_empty += bool(rows)
        for source, severity, first, second in rows:
            if first != second:
                reference[(source, frozenset((first, second)))] = severity

    result: dict = {"captures": len(captures), "captures_with_interactions": non_empty, "by_source": {}}
    for source in sorted({key[0] for key in reference}):
        outcome: Counter[str] = Counter()
        severity: Counter[str] = Counter()
        for (ref_source, pair), _ in reference.items():
            if ref_source != source:
                continue
            first, second = sorted(pair)
            if engine.concept(first) is None or engine.concept(second) is None:
                outcome["untestable_rxcui_not_in_current_rxnorm"] += 1
                continue
            rows = engine.conn.execute(
                "SELECT severity FROM interactions WHERE rxcui_a = ? AND rxcui_b = ?", (first, second)
            ).fetchall()
            if rows:
                outcome["listed"] += 1
                severity[rows[0][0]] += 1
            else:
                outcome["not_listed"] += 1
        total = sum(outcome.values())
        testable = total - outcome["untestable_rxcui_not_in_current_rxnorm"]
        result["by_source"][source] = {
            "distinct_pairs": total,
            "testable_pairs": testable,
            "outcome": dict(outcome),
            "listed_by_severity": dict(severity),
            "recall_of_testable": round(outcome["listed"] / testable, 4) if testable else None,
        }
    return result


# --------------------------------------------------------------------------- 3. Medicare Part D names


def evaluate_partd(engine: Engine, cache: Path, csv_path: Path | None) -> dict:
    path = csv_path or cached(PARTD_URL, cache / "medicare_part_d_spending_by_drug.csv")
    claims = {"generic": Counter(), "brand": Counter()}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["Mftr_Name"] != "Overall":
                continue
            try:
                count = float(row["Tot_Clms_2024"] or 0)
            except ValueError:
                count = 0.0
            claims["generic"][row["Gnrc_Name"].strip()] += count
            claims["brand"][row["Brnd_Name"].strip()] += count

    result: dict = {}
    for column, counter in claims.items():
        ranked = [name for name, _ in counter.most_common()]
        drugs = {name: engine.resolve_name(name) for name in ranked}
        section: dict = {"distinct_names": len(ranked)}
        for top in (100, 300, 1000):
            subset = ranked[:top]
            section[f"top_{top}_resolved"] = sum(drugs[name].resolved for name in subset)
        total = sum(counter.values())
        section["share_of_claims_resolved"] = round(sum(counter[n] for n in ranked if drugs[n].resolved) / total, 4)
        section["match_rules_top_300"] = dict(Counter(drugs[n].match for n in ranked[:300] if drugs[n].resolved))
        section["unresolved_in_top_100"] = [name for name in ranked[:100] if not drugs[name].resolved]
        result[column] = section
    return result


# --------------------------------------------------------------------------- 4. speed


def evaluate_speed(engine: Engine, rounds: int = 500) -> dict:
    ingredients = [row[0] for row in engine.conn.execute("SELECT DISTINCT rxcui_a FROM interactions")]
    rng = random.Random(20261115)
    result = {}
    for size in (2, 10, 25):
        timings = []
        for _ in range(rounds):
            picked = rng.sample(ingredients, size)
            started = time.perf_counter()
            engine.between([engine.resolve_rxcui(rxcui) for rxcui in picked])
            timings.append((time.perf_counter() - started) * 1000)
        timings.sort()
        result[f"{size}_drugs_ms"] = {
            "median": round(statistics.median(timings), 2),
            "p95": round(timings[int(len(timings) * 0.95)], 2),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=None, help="database to evaluate (default: configured one)")
    parser.add_argument("--cache", type=Path, default=None, help="where reference files are kept")
    parser.add_argument("--partd-csv", type=Path, default=None, help="use this copy of the CMS Part D file")
    parser.add_argument("--json", type=Path, default=None, help="also write the full results here")
    parser.add_argument("--skip", nargs="*", default=[], choices=["onc", "nlm", "partd", "speed"])
    args = parser.parse_args()

    database = args.db or config.db_path()
    cache = args.cache or database.parent / "evaluation-cache"
    engine = Engine(db.open_readonly(database))
    status = engine.status()
    results: dict = {
        "database": {
            "imported_at": status["imported_at"],
            "rxnorm_version": status["rxnorm_version"],
            "interactions": status["interactions"],
            "sources": [re.sub(r"\s+", " ", f"{s['name']} {s['version'] or ''}").strip() for s in status["sources"]],
        }
    }
    if "onc" not in args.skip:
        print("ONC high-priority list ...", file=sys.stderr)
        results["onc_high_priority"] = evaluate_onc(engine, cache)
    if "nlm" not in args.skip:
        print("Archived NLM responses ...", file=sys.stderr)
        results["nlm_archive"] = evaluate_nlm_archive(engine, cache)
    if "partd" not in args.skip:
        print("Medicare Part D drug names ...", file=sys.stderr)
        results["medicare_part_d_names"] = evaluate_partd(engine, cache, args.partd_csv)
    if "speed" not in args.skip:
        results["lookup_speed"] = evaluate_speed(engine)

    if args.json:
        args.json.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    summary = json.loads(json.dumps(results))
    summary.get("onc_high_priority", {}).pop("pairs_not_listed", None)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
