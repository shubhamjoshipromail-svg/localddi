"""Deterministic lookups against the imported database. No network, no model."""

from __future__ import annotations

import difflib
import json
import sqlite3
from dataclasses import dataclass, field

from .importer import SEVERITY_RANK
from .rxnorm import tty_rank
from .textnorm import normalize_name, rewrites, split_combination

MAX_DRUGS = 50  # same limit as the NLM list endpoint
SUGGESTION_TTYS = ("IN", "PIN", "MIN", "BN")


@dataclass
class Concept:
    rxcui: str
    name: str
    tty: str

    def as_dict(self) -> dict:
        return {"rxcui": self.rxcui, "name": self.name, "tty": self.tty}


@dataclass
class Drug:
    """One drug as the caller supplied it, and what it resolved to."""

    input: str
    input_type: str  # "name" or "rxcui"
    resolved: bool = False
    concept: Concept | None = None
    # exact | alias | source-name | qualifier-stripped | normalized | salt-stripped | combination | rxcui
    match: str | None = None
    reason: str | None = None  # why it did not resolve
    ingredients: list[Concept] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "input": self.input,
            "input_type": self.input_type,
            "resolved": self.resolved,
            "rxcui": self.concept.rxcui if self.concept else None,
            "name": self.concept.name if self.concept else None,
            "tty": self.concept.tty if self.concept else None,
            "match": self.match,
            "reason": self.reason,
            "ingredients": [{"rxcui": c.rxcui, "name": c.name} for c in self.ingredients],
            "suggestions": self.suggestions,
        }


@dataclass
class Finding:
    """One source statement that two ingredients interact, tied to the inputs that contain them."""

    source: str
    severity: str
    description: str | None
    management: str | None
    drug_a: Drug
    drug_b: Drug
    ingredient_a: Concept
    ingredient_b: Concept
    source_id_a: str
    source_id_b: str
    source_name_a: str
    source_name_b: str


class Engine:
    def __init__(self, conn: sqlite3.Connection, min_severity: str | None = None):
        self.conn = conn
        self.min_severity = min_severity  # server-wide floor; rows below it are never returned
        self._suggestion_pool: list[str] | None = None

    # ------------------------------------------------------------------ metadata

    def meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def sources(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM interactions i WHERE i.source = s.name) AS interactions "
            "FROM sources s ORDER BY s.name"
        ).fetchall()
        return [dict(row) for row in rows]

    def status(self) -> dict:
        report = json.loads(self.meta("report") or "{}")
        for source in report.get("sources", {}).values():
            unmatched = source.pop("unmatched_drugs", [])
            source["drugs_unmatched"] = len(unmatched)
        return {
            "imported_at": self.meta("imported_at"),
            "min_severity_floor": self.min_severity,
            "rxnorm_version": self.meta("rxnorm_version"),
            "interactions": self.conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0],
            "concepts": self.conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0],
            "sources": self.sources(),
            "import_report": report,
        }

    # ------------------------------------------------------------------ resolution

    def concept(self, rxcui: str) -> Concept | None:
        row = self.conn.execute("SELECT rxcui, name, tty FROM concepts WHERE rxcui = ?", (rxcui,)).fetchone()
        return Concept(row["rxcui"], row["name"], row["tty"]) if row else None

    def _ingredients(self, rxcui: str) -> list[Concept]:
        rows = self.conn.execute(
            "SELECT c.rxcui, c.name, c.tty FROM ingredient_map m JOIN concepts c ON c.rxcui = m.ingredient_rxcui "
            "WHERE m.rxcui = ? ORDER BY c.name",
            (rxcui,),
        ).fetchall()
        return [Concept(row["rxcui"], row["name"], row["tty"]) for row in rows]

    def resolve_rxcui(self, rxcui: str) -> Drug:
        rxcui = rxcui.strip()
        drug = Drug(input=rxcui, input_type="rxcui")
        concept = self.concept(rxcui)
        if concept is None:
            drug.reason = "unknown-rxcui"
            return drug
        drug.concept = concept
        drug.ingredients = self._ingredients(rxcui)
        if not drug.ingredients:
            drug.reason = "no-ingredient"
            return drug
        drug.resolved, drug.match = True, "rxcui"
        return drug

    def _lookup(self, norm: str, ingredient_only: bool = False) -> tuple[Concept, list[Concept], str] | None:
        """Exact lookup of one normalised key: (concept, ingredients, origin) or None."""
        rows = self.conn.execute("SELECT rxcui, tty, origin FROM names WHERE norm = ?", (norm,)).fetchall()
        if ingredient_only:
            rows = [row for row in rows if row["tty"] in ("IN", "PIN", "MIN")]
        if not rows:
            return None
        # RxNorm's own names win over spellings learned from an interaction source.
        origin_rank = {"rxnorm": 0, "alias": 1}
        best = min(
            rows,
            key=lambda r: (
                origin_rank.get(r["origin"], 2),
                tty_rank(r["tty"]),
                int(r["rxcui"]) if r["rxcui"].isdigit() else 10**12,
            ),
        )
        concept = self.concept(best["rxcui"])
        return concept, self._ingredients(best["rxcui"]), best["origin"]

    def _resolve_single(self, name: str) -> Drug:
        drug = Drug(input=name, input_type="name")
        for norm, rule in rewrites(name):
            hit = self._lookup(norm, ingredient_only=rule == "salt-stripped")
            if hit is None:
                continue
            drug.concept, drug.ingredients, origin = hit
            if not drug.ingredients:
                drug.reason = "no-ingredient"
                return drug
            drug.match = rule or {"rxnorm": "exact", "alias": "alias"}.get(origin, "source-name")
            drug.resolved = True
            return drug
        drug.reason = "unknown-name"
        return drug

    def resolve_name(self, name: str) -> Drug:
        """Resolve a drug name by exact lookup, then by the fixed rewrites in ``textnorm``.

        A name written as a combination ("A/B", "A-B", "A with B") resolves only
        if every part does. Nothing is matched by similarity.
        """
        drug = self._resolve_single(name)
        if drug.resolved or drug.reason == "no-ingredient":
            return drug
        parts = [self._resolve_single(part) for part in split_combination(name)]
        if parts and all(part.resolved for part in parts):
            ingredients = {c.rxcui: c for part in parts for c in part.ingredients}
            drug.ingredients = sorted(ingredients.values(), key=lambda c: c.name)
            # Use RxNorm's own multi-ingredient concept when one has exactly these ingredients.
            hit = self._lookup(normalize_name(" / ".join(c.name for c in drug.ingredients)))
            if hit and {c.rxcui for c in hit[1]} == set(ingredients):
                drug.concept = hit[0]
            drug.match, drug.reason, drug.resolved = "combination", None, True
            return drug
        drug.suggestions = self.suggest(name)
        return drug

    def suggest(self, name: str, limit: int = 5) -> list[str]:
        """Close spellings for an unknown name. Offered to the caller, never applied."""
        norm = normalize_name(name)
        if len(norm) < 3:
            return []
        if self._suggestion_pool is None:
            marks = ",".join("?" for _ in SUGGESTION_TTYS)
            rows = self.conn.execute(f"SELECT DISTINCT norm FROM names WHERE tty IN ({marks})", SUGGESTION_TTYS)
            self._suggestion_pool = [row[0] for row in rows]
        return difflib.get_close_matches(norm, self._suggestion_pool, n=limit, cutoff=0.8)

    # ------------------------------------------------------------------ interactions

    _SELECT = (
        "SELECT i.*, ca.name AS name_a, cb.name AS name_b, da.name AS source_name_a, db.name AS source_name_b "
        "FROM interactions i "
        "JOIN concepts ca ON ca.rxcui = i.rxcui_a JOIN concepts cb ON cb.rxcui = i.rxcui_b "
        "JOIN source_drugs da ON da.source = i.source AND da.source_id = i.a_source_id "
        "JOIN source_drugs db ON db.source = i.source AND db.source_id = i.b_source_id "
    )

    def _source_filter(self, sources: list[str] | None) -> tuple[str, list[str]]:
        clause, params = "", []
        if sources:
            marks = ",".join("?" for _ in sources)
            clause += f" AND LOWER(i.source) IN ({marks})"
            params += [name.lower() for name in sources]
        if self.min_severity:
            floor = SEVERITY_RANK[self.min_severity]
            allowed = [name for name, rank in SEVERITY_RANK.items() if rank >= floor]
            clause += f" AND i.severity IN ({','.join('?' for _ in allowed)})"
            params += allowed
        return clause, params

    def between(self, drugs: list[Drug], sources: list[str] | None = None) -> list[Finding]:
        """Interactions between different drugs in the list (never within one product)."""
        resolved = [drug for drug in drugs if drug.resolved]
        owners: dict[str, list[Drug]] = {}
        for drug in resolved:
            for ingredient in drug.ingredients:
                owners.setdefault(ingredient.rxcui, []).append(drug)
        if len(owners) < 2:
            return []
        marks = ",".join("?" for _ in owners)
        where, params = self._source_filter(sources)
        rows = self.conn.execute(
            f"{self._SELECT} WHERE i.rxcui_a IN ({marks}) AND i.rxcui_b IN ({marks}){where} ORDER BY i.id",
            [*owners, *owners, *params],
        ).fetchall()
        findings: list[Finding] = []
        for row in rows:
            for drug_a in owners[row["rxcui_a"]]:
                for drug_b in owners[row["rxcui_b"]]:
                    if drug_a is drug_b or _same_ingredients(drug_a, drug_b):
                        continue
                    findings.append(self._finding(row, drug_a, drug_b))
        findings.sort(key=lambda f: -SEVERITY_RANK[f.severity])
        return findings

    def for_drug(self, drug: Drug, sources: list[str] | None = None) -> list[Finding]:
        """Every stored interaction that involves one of the drug's ingredients."""
        if not drug.resolved:
            return []
        own = [c.rxcui for c in drug.ingredients]
        marks = ",".join("?" for _ in own)
        where, params = self._source_filter(sources)
        rows = self.conn.execute(
            f"{self._SELECT} WHERE (i.rxcui_a IN ({marks}) OR i.rxcui_b IN ({marks})){where} ORDER BY i.id",
            [*own, *own, *params],
        ).fetchall()
        findings = []
        for row in rows:
            if row["rxcui_a"] in own and row["rxcui_b"] in own:
                continue  # both halves are inside this one product
            findings.append(self._finding(row, drug, drug, flip=row["rxcui_b"] in own))
        return findings

    def _finding(self, row: sqlite3.Row, drug_a: Drug, drug_b: Drug, flip: bool = False) -> Finding:
        a, b = ("b", "a") if flip else ("a", "b")
        return Finding(
            source=row["source"],
            severity=row["severity"],
            description=row["description"],
            management=row["management"],
            drug_a=drug_a,
            drug_b=drug_b,
            ingredient_a=Concept(row[f"rxcui_{a}"], row[f"name_{a}"], "IN"),
            ingredient_b=Concept(row[f"rxcui_{b}"], row[f"name_{b}"], "IN"),
            source_id_a=row[f"{a}_source_id"],
            source_id_b=row[f"{b}_source_id"],
            source_name_a=row[f"source_name_{a}"],
            source_name_b=row[f"source_name_{b}"],
        )


def _same_ingredients(first: Drug, second: Drug) -> bool:
    return {c.rxcui for c in first.ingredients} == {c.rxcui for c in second.ingredients}


def highest_severity(findings: list[Finding]) -> str | None:
    if not findings:
        return None
    return max((finding.severity for finding in findings), key=SEVERITY_RANK.__getitem__)
