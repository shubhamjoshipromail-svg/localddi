# localddi

**A drug-drug interaction API you run yourself.** Send RxCUIs or drug names, get back the interactions listed in the data you imported. It serves the same JSON shape as the NLM RxNav Drug Interaction API that was [discontinued on 2 January 2024](https://lhncbc.nlm.nih.gov/RxNav/information/FAQs.html), so an integration that broke that day can point at your own server instead.

[![CI](https://github.com/shubhamjoshipromail-svg/localddi/actions/workflows/ci.yml/badge.svg)](https://github.com/shubhamjoshipromail-svg/localddi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
![Data: CC BY-NC-SA 4.0](https://img.shields.io/badge/default%20data-CC%20BY--NC--SA%204.0-orange.svg)

> [!WARNING]
> **Not for clinical use.** localddi is not a medical device and has not been clinically validated by anyone. The data is a third-party research database that can be incomplete, outdated or wrong, and localddi's matching of drug names can also be wrong. **A response with no interactions does not mean a combination is safe.** Do not use it to make treatment decisions.

> [!IMPORTANT]
> **The code is MIT. The default data is not.** `localddi import` downloads interaction data from [DDInter 2.0](https://ddinter2.scbdd.com), which is licensed **CC BY-NC-SA 4.0: non-commercial use only.** No interaction data is stored in this repository. For commercial use you need DDInter's permission or your own licensed data (`--csv`). Details: [docs/data-and-licensing.md](docs/data-and-licensing.md).

## Quickstart

You need Docker. Building and starting takes about a minute. The import is limited by NLM's download server: the 75 MB RxNorm file took me about ten minutes on the day I tested, and the import itself a few seconds. If you only want to see the API respond, use `--demo` (below) which needs no download at all.

```bash
git clone https://github.com/shubhamjoshipromail-svg/localddi
cd localddi
docker compose up -d --build
docker compose run --rm api localddi import
```

The import shows DDInter's licence terms and asks you to accept them (or pass `--accept-ddinter-license`). It then downloads RxNorm and DDInter, builds a SQLite database in a Docker volume, and prints what it matched. The running server picks the database up immediately.

Ask it something:

```bash
curl "http://localhost:8080/v1/interactions?drugs=warfarin,aspirin"
```

```json
{
  "disclaimer": "localddi is NOT a medical device and is NOT clinically validated. ...",
  "summary": {
    "drugs_resolved": 2,
    "drugs_unresolved": 0,
    "pairs_checked": 1,
    "interactions_found": 1,
    "highest_severity": "major",
    "by_severity": {"major": 1},
    "complete": true
  },
  "drugs": [
    {"input": "warfarin", "input_type": "name", "resolved": true, "rxcui": "11289", "name": "warfarin",
     "tty": "IN", "match": "exact", "reason": null,
     "ingredients": [{"rxcui": "11289", "name": "warfarin"}], "suggestions": []},
    {"input": "aspirin", "input_type": "name", "resolved": true, "rxcui": "1191", "name": "aspirin",
     "tty": "IN", "match": "exact", "reason": null,
     "ingredients": [{"rxcui": "1191", "name": "aspirin"}], "suggestions": []}
  ],
  "interactions": [
    {
      "severity": "major",
      "source": "DDInter",
      "description": null,
      "management": null,
      "drug_a": {"input": "warfarin", "rxcui": "11289", "name": "warfarin",
                 "source_id": "DDInter1951", "source_name": "Warfarin"},
      "drug_b": {"input": "aspirin", "rxcui": "1191", "name": "aspirin",
                 "source_id": "DDInter20", "source_name": "Acetylsalicylic acid"}
    }
  ],
  "sources": [
    {"name": "DDInter", "version": "2.0", "url": "https://ddinter2.scbdd.com/",
     "license": "CC BY-NC-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
     "attribution": "Interaction data from DDInter 2.0 ...", "interactions": 176263}
  ]
}
```

That is real output from an import run on 15 November 2026 (RxNorm release of 2 November 2026); your counts may differ as the upstream data changes.

The same question in the old NLM form, by RxCUI:

```bash
curl "http://localhost:8080/REST/interaction/list.json?rxcuis=207106+152923"
```

```json
{
  "nlmDisclaimer": "This response does not come from NLM. localddi is NOT a medical device ...",
  "fullInteractionTypeGroup": [
    {
      "sourceDisclaimer": "DDInter data is licensed for non-commercial use only (CC BY-NC-SA 4.0). ...",
      "sourceName": "DDInter",
      "fullInteractionType": [
        {
          "comment": "Drug1 (rxcui = 152923, name = simvastatin 40 MG Oral Tablet [Zocor], tty = SBD). Drug2 (rxcui = 207106, name = fluconazole 50 MG Oral Tablet [Diflucan], tty = SBD). Drug1 is resolved to simvastatin, Drug2 is resolved to fluconazole and interaction asserted in DDInter between Simvastatin and Fluconazole.",
          "minConcept": [
            {"rxcui": "152923", "name": "simvastatin 40 MG Oral Tablet [Zocor]", "tty": "SBD"},
            {"rxcui": "207106", "name": "fluconazole 50 MG Oral Tablet [Diflucan]", "tty": "SBD"}
          ],
          "interactionPair": [
            {
              "interactionConcept": [
                {"minConceptItem": {"rxcui": "36567", "name": "simvastatin", "tty": "IN"},
                 "sourceConceptItem": {"id": "DDInter1675", "name": "Simvastatin",
                                       "url": "https://ddinter2.scbdd.com/server/drug-detail/DDInter1675/"}},
                {"minConceptItem": {"rxcui": "4450", "name": "fluconazole", "tty": "IN"},
                 "sourceConceptItem": {"id": "DDInter743", "name": "Fluconazole",
                                       "url": "https://ddinter2.scbdd.com/server/drug-detail/DDInter743/"}}
              ],
              "severity": "major",
              "description": "DDInter lists a major interaction between Simvastatin and Fluconazole."
            }
          ]
        }
      ]
    }
  ]
}
```

Interactive API documentation is at <http://localhost:8080/docs> (OpenAPI at `/openapi.json`).

**Just want to see the response shapes first?** `docker compose run --rm api localddi import --demo` loads a tiny synthetic fixture instead: no download, no licensed data, and not real interaction data either.

### Without Docker

Python 3.10 or newer:

```bash
pip install -e .
localddi import
localddi serve            # http://127.0.0.1:8080
localddi check warfarin aspirin "Tylenol PM"
```

## What it does, and what it deliberately does not

- **Deterministic.** A lookup is a SQL query against a local SQLite file. The same request against the same import always gives the same response. There is no language model anywhere in it.
- **Offline after import.** The server makes no outbound network calls and needs no API key or account. Only `localddi import` uses the network, and it can run from files you fetched yourself (`--rxnorm-zip`, `--ddinter-dir`).
- **RxNorm-aware.** An input can be an ingredient, a US brand name, or a specific product (`simvastatin 40 MG Oral Tablet [Zocor]`); it is reduced to its ingredients using RxNorm's own relationships. A combination product is checked ingredient by ingredient.
- **No guessing at names.** A misspelt or unknown name comes back as `"resolved": false` with suggestions, and the summary says `"complete": false`. It is never silently matched to something else.
- **It carries the licence with the data.** Every response names its source, licence and attribution.
- **It does not** write its own interaction data, explain mechanisms, give dosing or management advice, check food, disease or allergy interactions, or store anything about requests.

## API

Native:

| Endpoint | Purpose |
|---|---|
| `GET /v1/interactions?drugs=a,b&rxcuis=1,2` | Check drugs against each other. Names and RxCUIs can be mixed. Options: `min_severity`, `sources`. |
| `POST /v1/interactions` | The same with a JSON body: `{"drugs": [...], "rxcuis": [...]}`. Keeps medication lists out of URLs and access logs. |
| `GET /v1/drugs/resolve?name=` | What a name resolves to in RxNorm. |
| `GET /v1/drugs/{rxcui}/interactions` | Everything the loaded data lists for one drug. |
| `GET /v1/status` | Loaded sources, their licences, counts, import date and the import report. |
| `GET /health` | Liveness. |

NLM-compatible (JSON only):

| Endpoint | NLM function |
|---|---|
| `GET /REST/interaction/list.json?rxcuis=A+B+C` | findInteractionsFromList |
| `GET /REST/interaction/interaction.json?rxcui=A` | findDrugInteractions |
| `GET /REST/interaction/sources.json` | getInteractionSources |

Severity is one of `contraindicated`, `major`, `moderate`, `minor`, `unknown`. DDInter uses the middle three plus "Unknown"; about 23% of the stored DDInter rows are "Unknown", meaning DDInter lists the pair without a level. Set `LOCALDDI_MIN_SEVERITY=minor` to leave those out of every response, or pass `min_severity` per request on the native API.

## Replacing the NLM API in an existing integration

The paths, parameters and JSON nesting match archived NLM responses, and a test compares the key structure against them. **The content is different**: `sourceName` is `DDInter` rather than `DrugBank`/`ONCHigh`, and descriptions are short generated sentences because DDInter's download files carry a severity level but no narrative. XML output is not implemented.

Read [docs/nlm-compatibility.md](docs/nlm-compatibility.md) before switching; it lists every known difference and includes the one-line change for OpenEMR. Nobody has reported running a production client against localddi yet, and it has not been tested inside OpenEMR. If you try it, an [integration report](https://github.com/shubhamjoshipromail-svg/localddi/issues/new?template=integration.yml) would help a lot.

## How much of the data is usable

Measured on the import of 15 November 2026 (all 14 DDInter files, RxNorm release 2026-11-02):

| | |
|---|---|
| Rows in the DDInter files | 507,655 |
| Unique drug pairs after removing duplicates | 234,981 |
| **Interactions stored and queryable** | **176,263 (75%)** |
| Pairs dropped because a drug had no RxNorm match | 58,718 (25%) |
| DDInter drugs matched to an RxNorm ingredient | 1,596 of 1,971 (81%) |
| Severity of stored rows | major 28,327 · moderate 100,708 · minor 6,776 · unknown 40,452 |

The unmatched 19% are mostly drugs no longer marketed in the United States (RxNorm's free subset covers currently prescribable US drugs), vaccines and herbal products named differently in the two vocabularies. Every unmatched name is written to `import-report.json`. This also means some names you might expect to work do not: `Coumadin`, for instance, is not in the current prescribable subset, while `warfarin` and `Jantoven` are.

Eleven well-known pairs were spot-checked by hand and came back as listed interactions (warfarin + aspirin, sildenafil + nitroglycerin, simvastatin + clarithromycin, methotrexate + trimethoprim, fluoxetine + tramadol, amiodarone + digoxin and others). That is a smoke test, not a validation. There has been no systematic comparison against a clinical reference.

One judgement call you should know about: DDInter's download page links 8 of its 14 per-category files. The other 6 (cardiovascular, genito-urinary, anti-infective, musculoskeletal, nervous system, sensory organs) sit in the same download directory on DDInter's server but are not linked. localddi downloads all 14 by default, because with only the linked 8 a pair such as sildenafil + nitroglycerin is missing. Pass `--ddinter-linked-only` if you would rather use only what the page links.

## Configuration

All optional, set as environment variables (see `.env.example`):

| Variable | Effect |
|---|---|
| `LOCALDDI_API_KEY` | Require this key (`X-API-Key` or `Authorization: Bearer`) on everything except `/health`. Off by default. |
| `LOCALDDI_MIN_SEVERITY` | Hide rows below this level in every endpoint, e.g. `minor` hides "unknown". |
| `LOCALDDI_CORS_ORIGINS` | Comma-separated browser origins to allow. None by default. |
| `LOCALDDI_PORT` | Host port for docker compose (default 8080, bound to 127.0.0.1). |
| `LOCALDDI_DATA_DIR` | Where the database and downloads live (default `./data`, `/data` in Docker). |

There is no built-in TLS, rate limiting or audit log. Put it behind your own reverse proxy if it leaves localhost; see [SECURITY.md](SECURITY.md).

To refresh the data, run the import again with `--refresh`. The database is rebuilt in a temporary file and swapped in atomically, so the server keeps answering.

## Using your own data

```bash
localddi import --no-ddinter --csv my_interactions.csv \
  --source-name "MySource" --source-license "Licensed to Example Clinic"
```

Columns: `drug_a`, `drug_b`, and optionally `severity`, `description`, `management`, `rxcui_a`, `rxcui_b`. See [docs/data-and-licensing.md](docs/data-and-licensing.md).

## Alternatives

Be sure this is the right tool:

- **A commercial clinical knowledge base** (First Databank, Medi-Span, Lexicomp, Micromedex, DrugBank's paid API). If the output reaches patients or prescribers, this is what you should be using. They are curated, maintained and licensed for clinical use; localddi is none of those.
- **Hosted replacement APIs** have appeared since the shutdown, including a commercial one called RxCheck. They save you running anything, at the cost of sending medication lists to a third party.
- **[PillChecker API](https://github.com/SPerekrestova/pillchecker-api)** (MIT): also DDInter-based, aimed at reading drug names from OCR text, with an FDA-label fallback classified by a model. It calls the RxNorm API at request time.
- **[RxNav-in-a-Box](https://lhncbc.nlm.nih.gov/RxNav/applications/RxNav-in-a-Box.html)** is NLM's own self-hosted RxNav. It is the right way to self-host RxNorm lookups. NLM's notice says RxNav's interaction features were discontinued; I have not installed it to check what it still contains.
- **DDInter's own website** has an interaction checker with mechanism and management text that its download files do not include.

What localddi adds is narrow: the NLM response shape, RxCUI in and out, fully offline operation, and no model in the loop.

## Development

```bash
pip install -e '.[dev]'
make test     # 134 tests, offline, about two seconds
make lint
```

The tests cover the API, the NLM-compatible structure, the importer on a small synthetic fixture, name normalisation, the downloader (against a local server) and a check that the server never opens a network connection. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Background

localddi was extracted from an earlier research prototype of a pharmacist-facing interaction checker. The patient records, the web interface and the language-model explanation layer were left behind; the deterministic lookup was kept and rebuilt around RxNorm files instead of live RxNorm API calls.

## Licence and citation

Code: [MIT](LICENSE). Data: not included, and under its publishers' terms, namely DDInter 2.0 (CC BY-NC-SA 4.0) and RxNorm Current Prescribable Content (public domain, U.S. National Library of Medicine). This project is not affiliated with or endorsed by NLM or DDInter.

If you use it in research, see [CITATION.cff](CITATION.cff), and please cite DDInter.
