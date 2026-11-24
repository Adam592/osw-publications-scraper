import argparse
from pathlib import Path

from osw_scraper.config import Settings
from osw_scraper.logging_config import setup_logging
from osw_scraper.pipeline import Pipeline
from osw_scraper.storage import Repository

EXIT_OK, EXIT_FAILED, EXIT_PARTIAL = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="osw-scraper", description="Scrape OSW publications into SQLite.")
    parser.add_argument("--db", type=Path, help="SQLite database path")
    parser.add_argument("--log-level", help="DEBUG, INFO, WARNING...")
    sub = parser.add_subparsers(dest="command", required=True)

    scrape = sub.add_parser("scrape", help="download publications into the database")
    scrape.add_argument("--max-pages", type=int)
    scrape.add_argument("--start-page", type=int)
    scrape.add_argument("--by-region", action="store_true", default=None)
    scrape.add_argument("--incremental", action="store_true", help="stop at the first page with nothing new")
    scrape.add_argument("--delay", type=float)
    scrape.add_argument("--headed", action="store_true", help="show the browser window")

    export = sub.add_parser("export", help="export the database to CSV")
    export.add_argument("--out", type=Path, default=Path("data/publications.csv"))

    sub.add_parser("stats", help="print a summary of the dataset")
    return parser


def cmd_stats(settings: Settings) -> int:
    with Repository(settings.db_path) as repo:
        print(f"Publications in database: {repo.count()}\n")
        print("By year and type:")
        for year, pub_type, n in repo.counts_by_year_and_type():
            print(f"  {year}  {pub_type:<25} {n:>5}")
        print("\nMost frequent authors:")
        for author, n in repo.top_authors():
            print(f"  {author:<35} {n:>5}")
        print("\nLast runs:")
        for run_id, started, status, pages, found, new, invalid in repo.last_runs():
            print(f"  #{run_id} {started} {status:<8} pages={pages} found={found} new={new} invalid={invalid}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env().with_overrides(db_path=args.db, log_level=args.log_level)

    if args.command == "scrape":
        settings = settings.with_overrides(
            max_pages=args.max_pages,
            start_page=args.start_page,
            by_region=args.by_region,
            delay_seconds=args.delay,
            stop_after_known_pages=1 if args.incremental else None,
            headless=False if args.headed else None,
        )

    setup_logging(settings.log_level, settings.log_dir)

    if args.command == "scrape":
        report = Pipeline(settings).run()
        return {"success": EXIT_OK, "partial": EXIT_PARTIAL}.get(report.status, EXIT_FAILED)
    if args.command == "export":
        with Repository(settings.db_path) as repo:
            repo.export_csv(args.out)
        return EXIT_OK
    return cmd_stats(settings)