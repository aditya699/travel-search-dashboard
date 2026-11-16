"""Command line for the pipeline. Run from ``server/``::

uv run python -m app.cli demo            # everything, offline, ten days of history
uv run python -m app.cli scrape          # today's scrape -> data/raw
uv run python -m app.cli clean           # LLM cleaning + checks -> data/clean
uv run python -m app.cli build           # DuckDB star schema + views
uv run python -m app.cli export          # CSV + Parquet for Power BI
uv run python -m app.cli eval            # score the cleaner (demo data only)
uv run python -m app.cli publish         # upload the .pbix to a Power BI workspace
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from app.catalog import Catalog
from app.clean.evaluate import evaluate
from app.clean.service import CleaningService
from app.container import load_catalog, make_llm
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging
from app.scrape.runner import scrape
from app.warehouse.build import build
from app.warehouse.export import export

logger = logging.getLogger("app.cli")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scrape", help="scrape every site in the search plan")
    p.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD")
    p.add_argument("--site", action="append", help="only this site key (repeatable)")

    p = sub.add_parser("clean", help="clean raw listings with the LLM and validate them")
    p.add_argument("--as-of", action="append", help="only this scrape date (repeatable)")

    sub.add_parser("build", help="rebuild the DuckDB warehouse")
    sub.add_parser("export", help="write CSV + Parquet for Power BI")

    p = sub.add_parser("demo", help="scrape N days of the demo sites, clean, build, export")
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--end", type=date.fromisoformat, default=date.today(), help="last scrape date")

    sub.add_parser("eval", help="field-by-field accuracy of the cleaner on demo data")

    p = sub.add_parser("publish", help="upload the .pbix to your Power BI workspace")
    p.add_argument("--pbix", help="path to the .pbix (default PBI_PBIX_PATH)")

    args = parser.parse_args(argv)
    # Listings contain ₹ and →; a Windows console in cp1252 would crash printing them.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    setup_logging("DEBUG" if args.verbose else "INFO")
    settings = get_settings()
    try:
        catalog = load_catalog(settings)
        return COMMANDS[args.command](settings, catalog, args)
    except AppError as exc:
        logger.error("%s", exc)
        return 1


def cmd_scrape(settings: Settings, catalog: Catalog, args: argparse.Namespace) -> int:
    report = scrape(settings, catalog, args.as_of, sites=args.site)
    print(f"Scraped {report.pages} pages, {report.cards} cards for {report.as_of}.")
    for error in report.errors[:10]:
        print(f"  ! {error}")
    return 0 if report.pages else 1


def cmd_clean(settings: Settings, catalog: Catalog, args: argparse.Namespace) -> int:
    service = CleaningService(settings, catalog, make_llm(settings, catalog))
    report = service.run(args.as_of)
    _print_clean(report)
    return 0 if not report.errors else 1


def cmd_build(settings: Settings, catalog: Catalog, args: argparse.Namespace) -> int:
    counts = build(settings, catalog)
    width = max(map(len, counts))
    for table, n in counts.items():
        print(f"  {table:<{width}}  {n:>7,}")
    return 0


def cmd_export(settings: Settings, catalog: Catalog, args: argparse.Namespace) -> int:
    files = export(settings)
    print(f"Wrote {len(files)} files to {settings.export_dir}")
    return 0


def cmd_demo(settings: Settings, catalog: Catalog, args: argparse.Namespace) -> int:
    if settings.scrape_mode != "demo":
        raise AppError("`demo` scrapes the built-in sites; set SCRAPE_MODE=demo.")
    days = [args.end - timedelta(days=k) for k in range(args.days - 1, -1, -1)]
    for day in days:
        report = scrape(settings, catalog, day)
        print(f"Scraped {day}: {report.pages} pages, {report.cards} cards")
    service = CleaningService(settings, catalog, make_llm(settings, catalog))
    _print_clean(service.run([d.isoformat() for d in days]))
    cmd_build(settings, catalog, args)
    cmd_export(settings, catalog, args)
    print("\nNext: `uv run python -m app.cli eval`, or start the API and open the dashboard.")
    return 0


def cmd_eval(settings: Settings, catalog: Catalog, args: argparse.Namespace) -> int:
    report = evaluate(settings, catalog)
    print(f"Scored {report.listings:,} listings. Every field right: {report.row_accuracy:.1%}\n")
    for name, accuracy in report.field_accuracy().items():
        bar = "#" * round(accuracy * 30)
        print(f"  {name:<20} {accuracy:7.2%}  {bar}")
    if report.examples:
        print("\nSome misses:")
        for example in report.examples[:5]:
            print(f"  {example['text'][:110]}")
            for w in example["wrong"]:
                print(f"    {w['field']}: got {w['got']!r}, want {w['want']!r}")
    return 0


def cmd_publish(settings: Settings, catalog: Catalog, args: argparse.Namespace) -> int:
    from pathlib import Path

    from app.powerbi.publish import get_token, publish_pbix

    if args.pbix:
        settings = settings.model_copy(update={"pbi_pbix_path": Path(args.pbix).resolve()})
    token = get_token(settings)
    result = publish_pbix(settings, token)
    print(f"Published. Report: {result.report_url or '(no report in the file)'}")
    if result.rls_roles_detected is False:
        print(
            "Warning: the semantic model has no RLS roles. Add the 'Desk' role (powerbi/README.md)."
        )
    elif result.rls_roles_detected:
        print("RLS roles found. Now add people to the 'Desk' role: semantic model → ⋯ → Security.")
    return 0


def _print_clean(report) -> None:
    status = ", ".join(f"{k} {v:,}" for k, v in sorted(report.status.items()))
    print(
        f"Cleaned {report.listings:,} listings ({report.cache_hits:,} from cache, "
        f"{report.llm_calls} LLM calls): {status}"
    )
    for error in report.errors[:10]:
        print(f"  ! {error}")


COMMANDS = {
    "scrape": cmd_scrape,
    "clean": cmd_clean,
    "build": cmd_build,
    "export": cmd_export,
    "demo": cmd_demo,
    "eval": cmd_eval,
    "publish": cmd_publish,
}


if __name__ == "__main__":
    sys.exit(main())
