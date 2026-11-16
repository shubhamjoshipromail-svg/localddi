"""HTTP API. Read-only, deterministic, and makes no outbound network calls."""

from __future__ import annotations

import hmac
import re
from collections.abc import Iterator
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import DISCLAIMER, REPO_URL, __version__, config, db, nlm
from .engine import MAX_DRUGS, Drug, Engine, Finding, highest_severity
from .importer import SEVERITIES

DESCRIPTION = f"""
Self-hosted drug-drug interaction lookups over data you import yourself.

**Not for clinical use.** {DISCLAIMER}

* `/v1/...` is the native API.
* `/REST/interaction/...` mirrors the JSON shape of the NLM RxNav Drug Interaction API that was
  discontinued on 2 January 2024, so existing integrations can point at this server instead.

Source: {REPO_URL}
"""

NO_DATA = (
    "No data has been imported yet. Run `localddi import` (or "
    "`docker compose run --rm api localddi import`) and try again."
)


class CheckRequest(BaseModel):
    drugs: list[str] = Field(default_factory=list, description="Drug names (generic or US brand).")
    rxcuis: list[str] = Field(default_factory=list, description="RxNorm concept identifiers.")
    sources: list[str] = Field(default_factory=list, description="Restrict to these source names.")
    min_severity: str | None = Field(default=None, description="Lowest severity to return.")


def _split(values: list[str] | None, pattern: str = r"[,+\s]+") -> list[str]:
    """Accept repeated parameters and delimiter-separated lists alike."""
    items: list[str] = []
    for value in values or []:
        items.extend(part.strip() for part in re.split(pattern, value) if part.strip())
    return items


def _interaction_json(finding: Finding) -> dict:
    def side(drug: Drug, ingredient, source_id: str, source_name: str) -> dict:
        return {
            "input": drug.input,
            "rxcui": ingredient.rxcui,
            "name": ingredient.name,
            "source_id": source_id,
            "source_name": source_name,
        }

    return {
        "severity": finding.severity,
        "source": finding.source,
        "description": finding.description,
        "management": finding.management,
        "drug_a": side(finding.drug_a, finding.ingredient_a, finding.source_id_a, finding.source_name_a),
        "drug_b": side(finding.drug_b, finding.ingredient_b, finding.source_id_b, finding.source_name_b),
    }


def _source_json(source: dict) -> dict:
    keys = ("name", "version", "url", "license", "license_url", "attribution", "interactions")
    return {key: source.get(key) for key in keys}


def _filter_severity(findings: list[Finding], min_severity: str | None) -> list[Finding]:
    if not min_severity:
        return findings
    level = min_severity.strip().lower()
    if level not in SEVERITIES:
        raise HTTPException(400, f"min_severity must be one of {', '.join(SEVERITIES)}")
    order = list(reversed(SEVERITIES))
    return [finding for finding in findings if order.index(finding.severity) >= order.index(level)]


def create_app(database: Path | None = None) -> FastAPI:
    app = FastAPI(
        title="localddi",
        version=__version__,
        description=DESCRIPTION,
        license_info={"name": "MIT (code). Imported data keeps its own licence; see /v1/status."},
    )
    origins = config.cors_origins()
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])

    def get_engine() -> Iterator[Engine]:
        path = database or config.db_path()
        try:
            conn = db.open_readonly(path)
        except FileNotFoundError:
            raise HTTPException(503, NO_DATA) from None
        try:
            yield Engine(conn, config.min_severity())
        finally:
            conn.close()

    def require_key(request: Request) -> None:
        expected = config.api_key()
        if not expected:
            return
        supplied = request.headers.get("x-api-key") or ""
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            supplied = auth[7:].strip()
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(401, "Missing or wrong API key (send X-API-Key or Authorization: Bearer).")

    protected = [Depends(require_key)]

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    # ------------------------------------------------------------------ service

    @app.get("/health", tags=["service"], summary="Liveness check")
    def health() -> dict:
        path = database or config.db_path()
        return {"status": "ok", "version": __version__, "data_loaded": path.exists()}

    @app.get("/v1/status", tags=["service"], summary="What data is loaded, and under which licence",
             dependencies=protected)
    def status(engine: Engine = Depends(get_engine)) -> dict:
        return {"version": __version__, "disclaimer": DISCLAIMER, **engine.status()}

    # ------------------------------------------------------------------ native API

    def run_check(engine: Engine, names: list[str], rxcuis: list[str], sources: list[str],
                  min_severity: str | None) -> dict:
        if not names and not rxcuis:
            raise HTTPException(400, "Give at least one drug: ?drugs=warfarin,aspirin or ?rxcuis=11289,1191")
        if len(names) + len(rxcuis) > MAX_DRUGS:
            raise HTTPException(400, f"At most {MAX_DRUGS} drugs per request.")
        drugs = [engine.resolve_name(name) for name in names] + [engine.resolve_rxcui(r) for r in rxcuis]
        findings = _filter_severity(engine.between(drugs, sources or None), min_severity)
        resolved = sum(1 for drug in drugs if drug.resolved)
        return {
            "disclaimer": DISCLAIMER,
            "summary": {
                "drugs_resolved": resolved,
                "drugs_unresolved": len(drugs) - resolved,
                "pairs_checked": resolved * (resolved - 1) // 2,
                "interactions_found": len(findings),
                "highest_severity": highest_severity(findings),
                "by_severity": {
                    level: count
                    for level in SEVERITIES
                    if (count := sum(1 for finding in findings if finding.severity == level))
                },
                # False means some input was not recognised, so the answer is incomplete.
                "complete": resolved == len(drugs),
            },
            "drugs": [drug.as_dict() for drug in drugs],
            "interactions": [_interaction_json(finding) for finding in findings],
            "sources": [_source_json(s) for s in engine.sources()],
        }

    @app.get("/v1/interactions", tags=["native"], summary="Check a list of drugs against each other",
             dependencies=protected)
    def check_get(
        drugs: list[str] | None = Query(None, description="Drug names, comma-separated or repeated."),
        rxcuis: list[str] | None = Query(None, description="RxCUIs, comma-, space- or plus-separated."),
        sources: list[str] | None = Query(None, description="Restrict to these source names."),
        min_severity: str | None = Query(None, description="minor, moderate, major or contraindicated."),
        engine: Engine = Depends(get_engine),
    ) -> dict:
        return run_check(engine, _split(drugs, r"\s*,\s*"), _split(rxcuis), _split(sources), min_severity)

    @app.post("/v1/interactions", tags=["native"], summary="Same check, with a JSON body",
              dependencies=protected)
    def check_post(body: CheckRequest, engine: Engine = Depends(get_engine)) -> dict:
        names = [name.strip() for name in body.drugs if name.strip()]
        rxcuis = [rxcui.strip() for rxcui in body.rxcuis if rxcui.strip()]
        return run_check(engine, names, rxcuis, body.sources, body.min_severity)

    @app.get("/v1/drugs/resolve", tags=["native"], summary="Normalise a drug name to RxNorm",
             dependencies=protected)
    def resolve(name: str = Query(..., min_length=1), engine: Engine = Depends(get_engine)) -> dict:
        return engine.resolve_name(name).as_dict()

    @app.get("/v1/drugs/{rxcui}/interactions", tags=["native"],
             summary="Everything the loaded sources list for one drug", dependencies=protected)
    def drug_interactions(
        rxcui: str,
        sources: list[str] | None = Query(None),
        min_severity: str | None = Query(None),
        engine: Engine = Depends(get_engine),
    ) -> dict:
        drug = engine.resolve_rxcui(rxcui)
        if drug.concept is None:
            raise HTTPException(404, f"RxCUI {rxcui} is not in the loaded RxNorm release.")
        findings = _filter_severity(engine.for_drug(drug, _split(sources) or None), min_severity)
        return {
            "disclaimer": DISCLAIMER,
            "drug": drug.as_dict(),
            "interactions_found": len(findings),
            "interactions": [
                {
                    "severity": f.severity,
                    "source": f.source,
                    "description": f.description,
                    "management": f.management,
                    "ingredient": {"rxcui": f.ingredient_a.rxcui, "name": f.ingredient_a.name},
                    "interacts_with": {
                        "rxcui": f.ingredient_b.rxcui,
                        "name": f.ingredient_b.name,
                        "source_id": f.source_id_b,
                        "source_name": f.source_name_b,
                    },
                }
                for f in findings
            ],
            "sources": [_source_json(s) for s in engine.sources()],
        }

    # ------------------------------------------------------------------ NLM-compatible API

    def lowercase_params(request: Request) -> dict[str, str]:
        # NLM documented its query parameters as case-insensitive.
        return {key.lower(): value for key, value in request.query_params.items()}

    @app.get("/REST/interaction/list.json", tags=["nlm-compatible"], dependencies=protected,
             summary="Interactions between a list of RxCUIs (NLM findInteractionsFromList shape)")
    def nlm_list(
        request: Request,
        rxcuis: str | None = Query(None, description="Space- or plus-separated RxCUIs, at most 50."),
        sources: str | None = Query(None, description="Space-separated source names."),
        engine: Engine = Depends(get_engine),
    ) -> dict:
        params = lowercase_params(request)
        ids = _split([params.get("rxcuis", "")])
        if not ids:
            raise HTTPException(400, "The rxcuis parameter is required, e.g. ?rxcuis=11289+1191")
        if len(ids) > MAX_DRUGS:
            raise HTTPException(400, f"At most {MAX_DRUGS} RxCUIs per request.")
        return nlm.interaction_list(engine, ids, _split([params.get("sources", "")]) or None)

    @app.get("/REST/interaction/interaction.json", tags=["nlm-compatible"], dependencies=protected,
             summary="All interactions of one RxCUI (NLM findDrugInteractions shape)")
    def nlm_single(
        request: Request,
        rxcui: str | None = Query(None, description="One RxCUI."),
        sources: str | None = Query(None, description="Space-separated source names."),
        engine: Engine = Depends(get_engine),
    ) -> dict:
        params = lowercase_params(request)
        value = params.get("rxcui", "").strip()
        if not value:
            raise HTTPException(400, "The rxcui parameter is required, e.g. ?rxcui=11289")
        return nlm.interaction_single(engine, value, _split([params.get("sources", "")]) or None)

    @app.get("/REST/interaction/sources.json", tags=["nlm-compatible"], dependencies=protected,
             summary="Names of the loaded interaction sources (NLM getInteractionSources shape)")
    def nlm_sources(engine: Engine = Depends(get_engine)) -> dict:
        return nlm.source_list(engine)

    @app.get("/REST/interaction/{name}", include_in_schema=False)
    def nlm_other(name: str) -> JSONResponse:
        return JSONResponse(
            {"error": f"/REST/interaction/{name} is not implemented. Only the .json forms of interaction, "
                      "list and sources exist here; XML output is not supported."},
            status_code=404,
        )

    return app


app = create_app()
