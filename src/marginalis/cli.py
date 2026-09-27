"""Command-line entry point: `uv run marginalis <command> ...`."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from marginalis.config import BAS, DATA_END, DATA_START


def _date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def cmd_ingest(args: argparse.Namespace) -> None:
    from marginalis.ingestion import eia, grid_monitor_xlsx, weather

    for ba in args.ba:
        if "eia" in args.sources:
            for route in eia.ROUTES:
                eia.fetch_range(route, ba, args.start, args.end, force=args.force)
        if "weather" in args.sources:
            weather.fetch_ba(ba, args.start, args.end, force=args.force)
        if "grid_monitor" in args.sources:
            grid_monitor_xlsx.build(ba, force_download=args.force)


def cmd_build(args: argparse.Namespace) -> None:
    from marginalis import db
    from marginalis.transform import build

    with db.connect() as conn:
        db.migrate(conn)
        build.load_reference(conn)
        for ba in args.ba:
            build.load_ba(conn, ba, build.build_ba(ba))


def cmd_report(args: argparse.Namespace) -> None:
    from marginalis import db, quality_report

    with db.connect() as conn:
        quality_report.write(conn)


def cmd_analyze(args: argparse.Namespace) -> None:
    from marginalis.analysis import findings

    findings.run()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="marginalis")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    ing = sub.add_parser("ingest", help="pull raw data into data/raw/")
    ing.add_argument("--ba", nargs="+", choices=list(BAS), default=list(BAS))
    sources = ["eia", "weather", "grid_monitor"]
    ing.add_argument("--sources", nargs="+", choices=sources, default=sources)
    ing.add_argument("--start", type=_date, default=DATA_START, help="YYYY-MM-DD (UTC)")
    ing.add_argument("--end", type=_date, default=DATA_END, help="YYYY-MM-DD, exclusive")
    ing.add_argument("--force", action="store_true", help="re-fetch files already on disk")
    ing.set_defaults(func=cmd_ingest)

    bld = sub.add_parser("build", help="clean, validate and load raw data into Postgres")
    bld.add_argument("--ba", nargs="+", choices=list(BAS), default=list(BAS))
    bld.set_defaults(func=cmd_build)

    rep = sub.add_parser("report", help="write reports/data_quality.md")
    rep.set_defaults(func=cmd_report)

    ana = sub.add_parser("analyze", help="train-split EDA + MEF estimation -> mef_profile, eda_findings.md")
    ana.set_defaults(func=cmd_analyze)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args.func(args)


if __name__ == "__main__":
    main()
