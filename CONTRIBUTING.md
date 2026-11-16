# Contributing

Thanks for looking. This is a small project with a narrow job: answer "do these drugs interact?" from data the operator imported, deterministically, with no outside calls at request time.

## Set up

```bash
git clone https://github.com/shubhamjoshipromail-svg/localddi
cd localddi
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
make test
```

The tests run offline in a few seconds. They use a small fixture in `localddi/fixtures/`: real RxNorm rows for a handful of drugs (RxNorm prescribable content is public domain) and made-up interaction rows.

## Most useful contributions

1. **Integration reports.** If you point an existing RxNav interaction client at localddi, open an "Integration report" issue saying what worked and what your client needed that was missing. This is the main thing that decides what gets built next.
2. **Name matching.** `localddi import` writes `import-report.json`, which lists every source drug name it could not map to an RxNorm ingredient. Fixes are usually one line in `localddi/data/aliases.csv` (international name, RxNorm name). Please include a reference for the synonym.
3. **Importers for other data sources** with a clear licence. An importer is a function that yields `InteractionRow` objects; see `read_ddinter_dir` in `localddi/importer.py`.
4. **XML output** for the NLM-compatible endpoints, if you have a client that needs it.

## Rules that will not bend

- **No interaction data or RxNorm release files in the repository.** DDInter is CC BY-NC-SA 4.0 and cannot be redistributed under this repository's MIT licence. Test fixtures must be synthetic or public domain.
- **Detection stays deterministic.** No model calls and no network calls in the request path. A test (`tests/test_offline.py`) fails if the server opens a socket while answering.
- **No fuzzy auto-matching of drug names.** A misspelt name returns suggestions and `resolved: false`; it is never silently mapped to a different drug.
- **Do not weaken the disclaimers.** This is not a clinical decision support system.

## Pull requests

Keep them small. Run `make test` and `make lint`. Describe how you checked the change. If behaviour changes, add a line to `CHANGELOG.md`.
