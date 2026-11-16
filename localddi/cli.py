"""Command line: ``localddi demo | import | serve | check | status``."""

from __future__ import annotations

import argparse
import json
import sys
from importlib import resources
from pathlib import Path

from . import DISCLAIMER, __version__, config, db
from .importer import DDINTER_LICENSE, DDINTER_TERMS_URL, Source, build_database, ddinter_source, read_generic_csv

LICENSE_NOTICE = f"""
DDInter data licence
--------------------
The interaction data is downloaded from DDInter 2.0 (https://ddinter2.scbdd.com).
DDInter publishes it under {DDINTER_LICENSE} ({DDINTER_TERMS_URL}):

  * NonCommercial - you may not use the data for commercial purposes.
  * Attribution   - you must credit DDInter.
  * ShareAlike    - if you share the data or anything built from it, use the same licence.

localddi's code is MIT, but that does not change the licence of this data.
If you need commercial use, import your own licensed data with --csv instead.
"""


def _fixture_dir() -> Path:
    return Path(str(resources.files("localddi").joinpath("fixtures")))


def cmd_import(args: argparse.Namespace) -> int:
    from . import download, rxnorm  # imported here so `serve` never loads network code

    out_path = Path(args.db) if args.db else config.db_path()
    cache = Path(args.cache_dir) if args.cache_dir else config.data_dir() / "downloads"
    sources: list[Source] = []

    if args.demo:
        print("Loading the bundled DEMO fixture: a few synthetic rows for trying the API. Not real data.")
        rx = rxnorm.load_dir(_fixture_dir() / "rrf", version="demo-fixture")
        sources.append(
            Source(
                name="DEMO",
                version="fixture",
                license="CC0-1.0 (synthetic fixture written for localddi's tests)",
                attribution="Synthetic demo rows shipped with localddi. Not a clinical data source.",
                disclaimer="DEMO DATA. A handful of made-up rows for testing the API. Never use it for real checks.",
                rows=read_generic_csv(_fixture_dir() / "demo_interactions.csv"),
            )
        )
    else:
        use_ddinter = not args.no_ddinter
        if use_ddinter and not args.accept_ddinter_license:
            print(LICENSE_NOTICE)
            if not sys.stdin.isatty():
                print("Re-run with --accept-ddinter-license to confirm you accept these terms.", file=sys.stderr)
                return 2
            if input("Do you accept these terms for your use? [y/N] ").strip().lower() not in {"y", "yes"}:
                print("Not accepted; nothing was downloaded.", file=sys.stderr)
                return 2
        if not use_ddinter and not args.csv:
            print("Nothing to import: --no-ddinter needs --csv.", file=sys.stderr)
            return 2

        if args.rxnorm_dir:
            rx = rxnorm.load_dir(Path(args.rxnorm_dir))
        else:
            zip_path = Path(args.rxnorm_zip) if args.rxnorm_zip else download.fetch_rxnorm(cache, args.refresh)
            print(f"Reading RxNorm from {zip_path}")
            rx = rxnorm.load_zip(zip_path)
        if use_ddinter:
            directory = (
                Path(args.ddinter_dir)
                if args.ddinter_dir
                else download.fetch_ddinter(cache, args.refresh, linked_only=args.ddinter_linked_only)
            )
            print(f"Reading DDInter from {directory}")
            present = {path.name for path in directory.glob("ddinter_downloads_code_*.csv")}
            missing = [name[-5] for name in download.DDINTER_FILES if name not in present]
            if missing:
                print(
                    f"WARNING: DDInter category file(s) {', '.join(sorted(missing))} are not in {directory}. "
                    "Interactions between drugs outside the categories you do have will be missing.",
                    file=sys.stderr,
                )
            sources.append(ddinter_source(directory))

    if args.csv:
        if not args.source_name or not args.source_license:
            print("--csv needs --source-name and --source-license.", file=sys.stderr)
            return 2
        sources.append(
            Source(name=args.source_name, license=args.source_license, rows=read_generic_csv(Path(args.csv)))
        )

    report = build_database(out_path, rx, sources)
    report_path = out_path.with_name("import-report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print_report(report)
    print(f"\nDatabase: {out_path}\nFull report (including every unmatched drug name): {report_path}")
    return 0


def print_report(report: dict) -> None:
    rx = report["rxnorm"]
    print(f"\nRxNorm {rx['version']}: {rx['concepts']:,} concepts, {rx['ingredients']:,} ingredients, "
          f"{rx['names']:,} names")
    for name, source in report["sources"].items():
        print(f"\n{name}")
        if source.get("files"):
            print(f"  files read                {len(source['files']):>9,}")
        print(f"  rows read                 {source['rows_read']:>9,}")
        print(f"  unique drug pairs         {source['unique_pairs']:>9,}")
        print(f"  interactions stored       {source['interactions_stored']:>9,}")
        print(f"  dropped: unmatched drug   {source['pairs_dropped_unmatched_drug']:>9,}")
        print(f"  dropped: same ingredient  {source['pairs_dropped_same_ingredient']:>9,}")
        print(f"  drugs matched to RxNorm   {source['drugs_matched']:>9,} of {source['drugs_total']:,}")
        print("  severity                  " + ", ".join(f"{k} {v:,}" for k, v in source["severity_counts"].items()))


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    if not config.db_path().exists():
        print(f"Warning: {config.db_path()} does not exist yet. The API will answer 503 until you run "
              "`localddi import`.", file=sys.stderr)
    uvicorn.run("localddi.app:app", host=args.host, port=args.port, log_level="info")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    if not config.db_path().exists():
        result = cmd_import(build_parser().parse_args(["import", "--demo"]))
        if result:
            return result
    host = "localhost" if args.host in {"0.0.0.0", "::"} else args.host
    if ":" in host:
        host = f"[{host}]"
    print(f"Open http://{host}:{args.port}", flush=True)
    return cmd_serve(args)


def _engine():
    from .engine import Engine

    try:
        return Engine(db.open_readonly(config.db_path()))
    except FileNotFoundError:
        print(f"No database at {config.db_path()}. Run `localddi import` first.", file=sys.stderr)
        raise SystemExit(1) from None


def cmd_check(args: argparse.Namespace) -> int:
    engine = _engine()
    drugs = [engine.resolve_rxcui(item) if item.isdigit() else engine.resolve_name(item) for item in args.drugs]
    for drug in drugs:
        if drug.resolved:
            names = ", ".join(c.name for c in drug.ingredients)
            rxcui = f"RxCUI {drug.concept.rxcui}, " if drug.concept else ""
            print(f"  {drug.input!r} -> {names} ({rxcui}{drug.match})")
        else:
            hint = f"; did you mean: {', '.join(drug.suggestions)}?" if drug.suggestions else ""
            print(f"  {drug.input!r} -> NOT RECOGNISED ({drug.reason}){hint}")
    findings = engine.between(drugs)
    if not findings:
        print("No interaction listed in the loaded data. This does not mean the combination is safe.")
    for finding in findings:
        text = f" - {finding.description}" if finding.description else ""
        print(f"  [{finding.severity.upper()}] {finding.ingredient_a.name} + {finding.ingredient_b.name} "
              f"({finding.source}){text}")
    print(f"\n{DISCLAIMER}")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    print(json.dumps(_engine().status(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="localddi", description=__doc__)
    parser.add_argument("--version", action="version", version=f"localddi {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="download the data and build the local database")
    imp.add_argument("--accept-ddinter-license", action="store_true",
                     help=f"confirm you accept DDInter's {DDINTER_LICENSE} terms (non-commercial use only)")
    imp.add_argument("--demo", action="store_true", help="load the tiny bundled synthetic fixture instead (no network)")
    imp.add_argument("--rxnorm-zip", help="use this RxNorm release zip instead of downloading")
    imp.add_argument("--rxnorm-dir", help="use this directory containing RXNCONSO.RRF and RXNREL.RRF")
    imp.add_argument("--ddinter-dir", help="use DDInter CSV files from this directory instead of downloading")
    imp.add_argument("--ddinter-linked-only", action="store_true",
                     help="download only the 8 files linked on DDInter's download page, not all 14")
    imp.add_argument("--no-ddinter", action="store_true", help="do not import DDInter (use with --csv)")
    imp.add_argument("--csv", help="also import your own interaction CSV (columns: drug_a, drug_b, severity, ...)")
    imp.add_argument("--source-name", help="name for the --csv source")
    imp.add_argument("--source-license", help="licence of the --csv data, shown in every response")
    imp.add_argument("--refresh", action="store_true", help="download again even if cached files exist")
    imp.add_argument("--cache-dir", help="where downloads are kept (default: <data dir>/downloads)")
    imp.add_argument("--db", help="output database path (default: <data dir>/localddi.sqlite)")
    imp.set_defaults(func=cmd_import)

    serve = sub.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.set_defaults(func=cmd_serve)

    demo = sub.add_parser("demo", help="load the synthetic fixture if no database exists, then serve the web page")
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--port", type=int, default=8080)
    demo.set_defaults(func=cmd_demo)

    check = sub.add_parser("check", help="check drugs from the command line (names or RxCUIs)")
    check.add_argument("drugs", nargs="+")
    check.set_defaults(func=cmd_check)

    status = sub.add_parser("status", help="show what data is loaded")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
