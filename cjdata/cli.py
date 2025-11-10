"""Command line interface for the cjdata package."""
from __future__ import annotations

import argparse
import logging
from typing import Sequence, Optional

from .builder import CJDataBuilder

DEFAULT_DB = "stock_data_hfq.db"


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cjdata", description="Local stock data toolkit")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO)")

    subparsers = parser.add_subparsers(dest="command")

    download = subparsers.add_parser("download", help="Perform a full data download")
    download.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    download.add_argument("--start-date", default="20080101", help="Start date in YYYYMMDD")
    download.add_argument("--end-date", help="End date in YYYYMMDD")
    download.add_argument("--include-dupont", action="store_true", help="Download DuPont data")
    download.add_argument("--skip-xtquant", action="store_true", help="Skip xtquant stage")
    download.add_argument("--skip-baostock", action="store_true", help="Skip baostock stage")

    update = subparsers.add_parser("update", help="Incrementally update existing data")
    update.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    update.add_argument("--end-date", help="End date in YYYYMMDD")
    update.add_argument("--skip-xtquant", action="store_true", help="Skip xtquant stage")
    update.add_argument("--skip-baostock", action="store_true", help="Skip baostock stage")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    _configure_logging(args.log_level)
    builder = CJDataBuilder(args.db)

    if args.command == "download":
        builder.bootstrap(
            start_date=args.start_date,
            end_date=args.end_date,
            include_dupont=args.include_dupont,
            skip_xtquant=args.skip_xtquant,
            skip_baostock=args.skip_baostock,
        )
    elif args.command == "update":
        builder.update(
            end_date=args.end_date,
            skip_xtquant=args.skip_xtquant,
            skip_baostock=args.skip_baostock,
        )
    else:
        parser.error(f"Unknown command: {args.command}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
