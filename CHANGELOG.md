# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

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
