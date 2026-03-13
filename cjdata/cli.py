"""Command line interface for the cjdata package."""
from __future__ import annotations

import argparse
import logging
from typing import Sequence, Optional

from .builder import CJDataBuilder, SMOKE_TEST_LIMIT

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
    download.add_argument("--skip-xtquant", action="store_true", help="Skip xtquant stage")
    download.add_argument("--skip-baostock", action="store_true", help="Skip baostock stage")
    download.add_argument("--skip-daily", action="store_true", help="Skip daily market data download")
    download.add_argument("--skip-dupont", action="store_true", help="Skip DuPont data download")
    download.add_argument("--only-dupont", action="store_true", help="Only download DuPont data (shortcut for --skip-xtquant --skip-daily)")
    download.add_argument("--smoke-test", action="store_true", help=f"Smoke-test mode: only download {SMOKE_TEST_LIMIT} stocks to verify correctness")

    update = subparsers.add_parser("update", help="Incrementally update existing data")
    update.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    update.add_argument("--end-date", help="End date in YYYYMMDD")
    update.add_argument("--skip-xtquant", action="store_true", help="Skip xtquant stage")
    update.add_argument("--skip-baostock", action="store_true", help="Skip baostock stage")
    update.add_argument("--skip-daily", action="store_true", help="Skip daily market data download")
    update.add_argument("--skip-dupont", action="store_true", help="Skip DuPont data download")
    update.add_argument("--only-dupont", action="store_true", help="Only update DuPont data (shortcut for --skip-xtquant --skip-daily)")
    update.add_argument("--smoke-test", action="store_true", help=f"Smoke-test mode: only download {SMOKE_TEST_LIMIT} stocks to verify correctness")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    _configure_logging(args.log_level)
    builder = CJDataBuilder(args.db)

    if getattr(args, "only_dupont", False) and args.skip_dupont:
        parser.error("--only-dupont cannot be combined with --skip-dupont")
    if getattr(args, "only_dupont", False) and args.skip_baostock:
        parser.error("--only-dupont cannot be combined with --skip-baostock")

    effective_skip_xtquant = args.skip_xtquant or getattr(args, "only_dupont", False)
    effective_skip_daily = args.skip_daily or getattr(args, "only_dupont", False)

    if args.command == "download":
        builder.bootstrap(
            start_date=args.start_date,
            end_date=args.end_date,
            skip_xtquant=effective_skip_xtquant,
            skip_baostock=args.skip_baostock,
            skip_daily=effective_skip_daily,
            skip_dupont=args.skip_dupont,
            smoke_test=args.smoke_test,
        )
    elif args.command == "update":
        builder.update(
            end_date=args.end_date,
            skip_xtquant=effective_skip_xtquant,
            skip_baostock=args.skip_baostock,
            skip_daily=effective_skip_daily,
            skip_dupont=args.skip_dupont,
            smoke_test=args.smoke_test,
        )
    else:
        parser.error(f"Unknown command: {args.command}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
