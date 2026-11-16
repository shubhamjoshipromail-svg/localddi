# Compatibility with the NLM RxNav Drug Interaction API

NLM discontinued the RxNav Drug Interaction API on 2 January 2024. localddi serves the same paths and the same JSON nesting, so a client written against NLM can be pointed at a localddi server. This page says exactly what matches, what does not, and how that was checked.

## What was checked, and against what

The response shapes were taken from two real NLM responses preserved by the Internet Archive, and from NLM's archived API documentation:

| Endpoint | Archived original |
|---|---|
| `list.json` | <https://web.archive.org/web/20220207074942/https://rxnav.nlm.nih.gov/REST/interaction/list.json?rxcuis=207106+152923+656659> |
| `interaction.json` | <https://web.archive.org/web/20210504130839/https://rxnav.nlm.nih.gov/REST/interaction/interaction.json?rxcui=341248> |
| `sources.json` | <https://web.archive.org/web/20211205192330/https://rxnav.nlm.nih.gov/REST/interaction/sources.json> |
| API docs | <https://web.archive.org/web/20230424111617/https://lhncbc.nlm.nih.gov/RxNav/APIs/api-Interaction.findInteractionsFromList.html> |

`tests/test_nlm_compat.py` asserts that localddi's responses have the same keys at every level as those archived responses. It does not compare content: the data is different (see below).

A separate [0.1.1 evaluation](evaluation.md#archived-nlm-responses) compares pair content across 52 archived responses. localddi lists only 883 of 3,050 testable DrugBank pairs (29%). DDInter covers far fewer pairs than DrugBank did in those captures. The archived drugs are not a designed sample, and this comparison is not clinical validation.

No live side-by-side comparison was possible, because the original service no longer exists. Nobody has yet reported running a production client against localddi. If you do, please open an "Integration report" issue.

## Endpoints

| NLM | localddi | Status |
|---|---|---|
| `GET /REST/interaction/list.json?rxcuis=A+B+C&sources=` | same | implemented |
| `GET /REST/interaction/interaction.json?rxcui=A&sources=` | same | implemented |
| `GET /REST/interaction/sources.json` | same | implemented |
| `GET /REST/interaction/version.json` | none | not implemented (returns 404) |
| `.xml` variants and the extension-less paths (XML was NLM's default) | none | not implemented (returns 404 with a JSON error) |

Behaviour kept from NLM:

- `rxcuis` is a space-separated list; `+` and `%20` both work. At most 50 identifiers.
- An RxCUI may be an ingredient, a brand name, or a clinical or branded drug. It is resolved to its ingredient(s) and the ingredients are checked.
- Query parameter names are case-insensitive.
- When nothing is found, the body contains only `nlmDisclaimer` (and `userInput` for `interaction.json`), with no `fullInteractionTypeGroup` / `interactionTypeGroup` key. Clients that test for that key, as OpenEMR does, behave the same way.
- Numbers are strings.

## Response shape

`list.json`:

```text
nlmDisclaimer
fullInteractionTypeGroup[]            one per data source
  sourceDisclaimer
  sourceName
  fullInteractionType[]               one per pair of input drugs that interact
    comment
    minConcept[2]                     the two inputs: rxcui, name, tty
    interactionPair[]
      interactionConcept[2]
        minConceptItem                the ingredient: rxcui, name, tty
        sourceConceptItem             the source's own id, name, url
      severity
      description
```

`interaction.json` is the same with `interactionTypeGroup[]` → `interactionType[]` → `minConceptItem`, plus a top-level `userInput` object.

## Differences you should know about

1. **The data is not NLM's.** NLM served DrugBank (non-commercial edition) and the ONC high-priority list. localddi serves whatever you imported, by default DDInter 2.0. `sourceName` is therefore `DDInter`, not `DrugBank` or `ONCHigh`. A client that filters on `sources=DrugBank` or reads only a group named `ONCHigh` will get nothing.
2. **`description` is generated when the source has none.** DDInter's download files carry a severity level but no narrative text, so the description reads, for example, `DDInter lists a major interaction between Warfarin and Acetylsalicylic acid.` DrugBank's mechanism sentences are not available.
3. **`severity` uses the source's levels.** DDInter rows give `major`, `moderate` or `minor`; rows DDInter marks "Unknown" are returned as `N/A`, which is what NLM returned for DrugBank rows. NLM's ONCHigh rows used `high`; nothing in localddi returns `high`.
4. **`nlmDisclaimer` keeps its key but not its text.** It states that the response does not come from NLM and repeats the not-for-clinical-use warning.
5. **`sourceDisclaimer` carries the data licence and attribution** of the imported source.
6. **`comment` follows NLM's wording pattern** but is assembled by localddi.
7. **Coverage differs.** Only drugs that localddi could match to an ingredient in RxNorm's *prescribable* subset are queryable. Even when both drugs resolve, the imported source may not list their pair. See [evaluation.md](evaluation.md) for the ONC, archived NLM and name-resolution comparisons, and [data-and-licensing.md](data-and-licensing.md) for import coverage.
8. **Unverified detail:** for `interaction.json` with a non-ingredient RxCUI (a brand or a tablet), `minConceptItem` is set to the input concept. The one archived response available used an ingredient as input, so it does not show which concept NLM placed there.

## Switching an existing client

If the base URL is configurable, change `https://rxnav.nlm.nih.gov` to your server, for example `http://localhost:8080`.

### OpenEMR

OpenEMR's prescription screen has the NLM URL hard-coded in `controllers/C_Prescription.class.php` (checked against the `master` branch in November 2026):

```php
$response = oeHttp::get('https://rxnav.nlm.nih.gov/REST/interaction/list.json?rxcuis=' . $rxcui_list);
```

The proposed patch changes the host in that line to your localddi server. OpenEMR's source reads `fullInteractionTypeGroup[0].fullInteractionType[*]` and prints `comment`, `minConcept[0].name`, `minConcept[1].name`, `interactionPair[0].severity` and `interactionPair[0].description`; localddi returns all of those fields.

**This has not been tested inside a running OpenEMR install.** It is based on reading OpenEMR's source and matching the fields it uses. Because OpenEMR reads only the first group, it will show one source's results if you import more than one.

Bear in mind DDInter's licence is non-commercial; see [data-and-licensing.md](data-and-licensing.md) before using it in a practice.
