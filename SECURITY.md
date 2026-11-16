# Security

## Reporting a vulnerability

Please report security problems privately through GitHub: **Security → Report a vulnerability** on this repository (private vulnerability reporting). Do not open a public issue for something exploitable.

Include what you found, how to reproduce it, and the version. You should get a first reply within a week. This is a one-maintainer project, so please allow time for a fix before disclosing.

## What to know before you deploy

- **No authentication by default.** The compose file binds the port to `127.0.0.1`. If you expose the service, set `LOCALDDI_API_KEY` or put it behind your own gateway. The key is a single shared secret, not a user system.
- **The server is read-only.** It opens the SQLite file read-only, stores nothing about requests, and makes no outbound network calls. It does not write an audit log; if you need one, log at your gateway.
- **Requests may contain medication lists.** Those can be sensitive health information. localddi does not persist them, but your reverse proxy or access logs might (drug names appear in query strings on `GET` requests; use `POST /v1/interactions` to keep them out of URLs).
- **The importer downloads over HTTPS** from `download.nlm.nih.gov` and `ddinter2.scbdd.com` and does not verify checksums (neither site publishes any). Run the import in an environment you trust, or pass files you obtained and checked yourself with `--rxnorm-zip` and `--ddinter-dir`.
- **Not a medical device.** A wrong or missing answer is a data-quality issue, not a security vulnerability, but please do report it as a "Data problem" issue.

## Supported versions

Only the latest release receives fixes.
