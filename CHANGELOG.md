# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.1.1] - 2026-11-15

### Added

- Fixed, ordered name rewrites after exact lookup fails: `qualifier-stripped`, `normalized` (abbreviations and trailing release words), `salt-stripped` (only if the remainder is an RxNorm ingredient), then `combination` (every part must resolve). The native API reports the rule in `match`. Suggestions are never applied automatically; there is still no fuzzy matching.
- Built-in alias from the discontinued brand Coumadin to warfarin.
- `scripts/evaluate.py`: reproducible comparisons with the expanded ONC high-priority list, archived NLM API responses and CMS Medicare Part D names, plus engine lookup timings. Reference data is downloaded at run time, not bundled. Methods and limits are in [docs/evaluation.md](docs/evaluation.md); the recorded results are in [docs/evaluation-results.json](docs/evaluation-results.json). These measurements are not clinical validation.
- Import warning if any of the 14 DDInter ATC category files is missing.

### Changed

- Updated import figures for all 14 DDInter files and RxNorm prescribable release 2026-11-02: 176,817 interactions stored; 58,164 pairs dropped for an unmatched drug; 1,598 of 1,971 DDInter drugs matched (1,402 exact, 173 qualifier-stripped, 23 aliases), with 373 unmatched.
- Documented the measured limits: 721 of 793 testable ONC pairs listed (90.9%), but only 883 of 3,050 testable archived DrugBank pairs (29%). DDInter covers far fewer pairs in those captures. Top-100 CMS name resolution is 94 generic and 96 brand names, up from 70 and 68 before the rewrite rules.
- Offline test suite now contains 158 tests.

## [0.1.0] - 2026-11-15

First public release.

### Added

- `localddi import`: downloads RxNorm Current Prescribable Content (public domain) and DDInter 2.0 (CC BY-NC-SA 4.0, after explicit acceptance), matches DDInter drug names to RxNorm ingredients, and builds a local SQLite database. Writes a report of everything it could not match.
- `localddi import --demo`: a tiny synthetic fixture for trying the API with no network and no licensed data.
- `localddi import --csv`: bring your own interaction data under your own licence.
- Native API: `GET`/`POST /v1/interactions` (by drug name and/or RxCUI), `GET /v1/drugs/resolve`, `GET /v1/drugs/{rxcui}/interactions`, `GET /v1/status`.
- NLM-compatible API: `/REST/interaction/list.json`, `/REST/interaction/interaction.json`, `/REST/interaction/sources.json`, following archived NLM responses. JSON only.
- `localddi check` and `localddi status` command-line tools.
- Docker image and compose file; optional shared API key; optional CORS.
- OpenAPI documentation at `/docs`.

### Known limits

- Not clinically validated. Not a medical device.
- No XML output and no `version.json` on the NLM-compatible endpoints.
- Not yet tested inside a real OpenEMR install or any other production client.
- DDInter drugs that are not in RxNorm's prescribable subset are not queryable.
- DDInter's download files contain severity levels only, so descriptions are generated sentences, not mechanism text.

[0.1.0]: https://github.com/shubhamjoshipromail-svg/localddi/releases/tag/v0.1.0
