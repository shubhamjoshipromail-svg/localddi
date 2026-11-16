"""Shape results like the discontinued NLM RxNav Drug Interaction API.

The field names and nesting follow archived responses of
``/REST/interaction/interaction.json`` and ``/REST/interaction/list.json``
(see docs/nlm-compatibility.md). The *content* is different: the data comes
from whatever source was imported locally, not from NLM, DrugBank or ONCHigh.
"""

from __future__ import annotations

from . import DISCLAIMER
from .engine import Concept, Drug, Engine, Finding

NLM_DISCLAIMER = "This response does not come from NLM. " + DISCLAIMER

SOURCE_DRUG_URLS = {"DDInter": "https://ddinter2.scbdd.com/server/drug-detail/{id}/"}


def _severity(value: str) -> str:
    # NLM used "N/A" when a source carried no severity.
    return "N/A" if value == "unknown" else value


def _description(finding: Finding) -> str:
    if finding.description:
        return finding.description
    level = "an" if finding.severity == "unknown" else f"a {finding.severity}"
    suffix = " interaction of unclassified severity" if finding.severity == "unknown" else " interaction"
    return f"{finding.source} lists {level}{suffix} between {finding.source_name_a} and {finding.source_name_b}."


def _source_concept(source: str, source_id: str, name: str) -> dict:
    template = SOURCE_DRUG_URLS.get(source)
    return {"id": source_id, "name": name, "url": template.format(id=source_id) if template else "NA"}


def _pair(finding: Finding) -> dict:
    return {
        "interactionConcept": [
            {
                "minConceptItem": finding.ingredient_a.as_dict(),
                "sourceConceptItem": _source_concept(finding.source, finding.source_id_a, finding.source_name_a),
            },
            {
                "minConceptItem": finding.ingredient_b.as_dict(),
                "sourceConceptItem": _source_concept(finding.source, finding.source_id_b, finding.source_name_b),
            },
        ],
        "severity": _severity(finding.severity),
        "description": _description(finding),
    }


def _source_disclaimers(engine: Engine) -> dict[str, str]:
    result = {}
    for source in engine.sources():
        parts = [source.get("disclaimer"), source.get("attribution"), f"License: {source['license']}."]
        result[source["name"]] = " ".join(part for part in parts if part)
    return result


def _min_concept(concept: Concept | None) -> dict:
    return concept.as_dict() if concept else {}


def interaction_list(engine: Engine, rxcuis: list[str], sources: list[str] | None) -> dict:
    """Body for ``/REST/interaction/list.json``."""
    drugs = [engine.resolve_rxcui(rxcui) for rxcui in rxcuis]
    findings = engine.between(drugs, sources)
    body: dict = {"nlmDisclaimer": NLM_DISCLAIMER}
    if not findings:
        return body
    disclaimers = _source_disclaimers(engine)
    groups: dict[str, dict[tuple[int, int], dict]] = {}
    for finding in findings:
        drug_a, drug_b = finding.drug_a, finding.drug_b
        key = (id(drug_a), id(drug_b))
        per_source = groups.setdefault(finding.source, {})
        entry = per_source.get(key)
        if entry is None:
            entry = per_source[key] = {
                "comment": _list_comment(drug_a, drug_b, finding),
                "minConcept": [_min_concept(drug_a.concept), _min_concept(drug_b.concept)],
                "interactionPair": [],
            }
        entry["interactionPair"].append(_pair(finding))
    body["fullInteractionTypeGroup"] = [
        {
            "sourceDisclaimer": disclaimers.get(source, ""),
            "sourceName": source,
            "fullInteractionType": list(entries.values()),
        }
        for source, entries in groups.items()
    ]
    return body


def _list_comment(drug_a: Drug, drug_b: Drug, finding: Finding) -> str:
    def describe(label: str, drug: Drug) -> str:
        concept = drug.concept
        return f"{label} (rxcui = {concept.rxcui}, name = {concept.name}, tty = {concept.tty})"

    return (
        f"{describe('Drug1', drug_a)}. {describe('Drug2', drug_b)}. "
        f"Drug1 is resolved to {finding.ingredient_a.name}, Drug2 is resolved to {finding.ingredient_b.name} "
        f"and interaction asserted in {finding.source} between {finding.source_name_a} and {finding.source_name_b}."
    )


def interaction_single(engine: Engine, rxcui: str, sources: list[str] | None) -> dict:
    """Body for ``/REST/interaction/interaction.json``."""
    drug = engine.resolve_rxcui(rxcui)
    body: dict = {
        "nlmDisclaimer": NLM_DISCLAIMER,
        "userInput": {"sources": sources or [""], "rxcui": rxcui},
    }
    findings = engine.for_drug(drug, sources)
    if not findings:
        return body
    disclaimers = _source_disclaimers(engine)
    groups: dict[str, dict[str, dict]] = {}
    for finding in findings:
        per_source = groups.setdefault(finding.source, {})
        ingredient = finding.ingredient_a
        entry = per_source.get(ingredient.rxcui)
        if entry is None:
            entry = per_source[ingredient.rxcui] = {
                "comment": (
                    f"{drug.concept.name} ({drug.concept.rxcui}) is resolved to "
                    f"{ingredient.name} ({ingredient.rxcui})"
                ),
                "minConceptItem": drug.concept.as_dict(),
                "interactionPair": [],
            }
        entry["interactionPair"].append(_pair(finding))
    body["interactionTypeGroup"] = [
        {
            "sourceDisclaimer": disclaimers.get(source, ""),
            "sourceName": source,
            "interactionType": list(entries.values()),
        }
        for source, entries in groups.items()
    ]
    return body


def source_list(engine: Engine) -> dict:
    """Body for ``/REST/interaction/sources.json``."""
    return {"nlmDisclaimer": NLM_DISCLAIMER, "sourceList": {"source": [s["name"] for s in engine.sources()]}}
